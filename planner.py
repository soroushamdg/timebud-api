from datetime import datetime, timedelta
from math import exp
from uuid import uuid4
from typing import List, Dict, Optional, Any

# Configuration constants
URGENCY_K = 3.5
PROJECT_PRI_SCORE = 2.0
PROJECT_DEF_SCORE = 1.0
SOLO_BUCKET_PRI = 2.0
SOLO_BUCKET_DEF = 1.0
MIN_ALLOCATION = 10
PARTIAL_FLOOR = 0
DEFAULT_ESTIMATE = 25
NO_DEADLINE_DAYS = 30
SOLO_BUCKET_ID = '__solo__'


def plan_session(
    projects: List[Dict[str, Any]],
    milestones: List[Dict[str, Any]], 
    tasks: List[Dict[str, Any]],
    budget_minutes: int
) -> Dict[str, Any]:
    """
    Plan a work session by allocating time across projects and tasks.
    
    Args:
        projects: List of project dicts with keys: id, name, deadline, priority, status
        milestones: List of milestone dicts with keys: id, project_id, title, order
        tasks: List of task dicts with keys: id, project_id, milestone_id, title, 
                estimated_minutes, status, due_date, order, priority, depends_on_task
        budget_minutes: Total time available for the session
        
    Returns:
        Plan dict with session details and scheduled tasks
    """
    # Filter to pending tasks only
    pending_tasks = [t for t in tasks if t['status'] == 'pending']
    
    # Track scheduled tasks and remaining budget
    scheduled_tasks = []
    remaining_budget = budget_minutes
    
    # STAGE 0: Schedule tier-1 tasks first
    tier1_tasks = []
    other_tasks = []
    
    for task in pending_tasks:
        if (task['project_id'] is None and 
            task['milestone_id'] is None and 
            task['priority'] is True and 
            task['due_date'] is not None):
            tier1_tasks.append(task)
        else:
            other_tasks.append(task)
    
    # Sort tier-1 tasks by nearest deadline
    tier1_tasks.sort(key=lambda t: t['due_date'])
    
    # Schedule tier-1 tasks greedily
    position = 0
    for task in tier1_tasks:
        if remaining_budget <= 0:
            break
            
        estimate = task['estimated_minutes'] or DEFAULT_ESTIMATE
        scheduled_mins = min(estimate, remaining_budget)
        
        scheduled_tasks.append({
            'position': position,
            'task_id': task['id'],
            'project_id': task['project_id'],
            'is_solo': True,
            'tier1': True,
            'milestone_title': None,
            'title': task['title'],
            'priority': task['priority'],
            'scheduled_minutes': scheduled_mins,
            'partial': scheduled_mins < estimate,
            'carry_over_minutes': estimate - scheduled_mins
        })
        
        remaining_budget -= scheduled_mins
        position += 1
    
    if remaining_budget <= 0:
        return _format_plan_result(budget_minutes, scheduled_tasks)
    
    # STAGE 1: Allocate remaining budget across projects and tier-2 solo tasks
    # Build buckets
    buckets = []
    
    # Project buckets
    active_projects = [p for p in projects if p['status'] == 'active']
    for project in active_projects:
        project_tasks = [t for t in other_tasks if t['project_id'] == project['id']]
        if not project_tasks:
            continue
            
        # Calculate project metrics
        total_minutes = sum(t['estimated_minutes'] or DEFAULT_ESTIMATE for t in project_tasks)
        pending_minutes = sum(t['estimated_minutes'] or DEFAULT_ESTIMATE 
                            for t in project_tasks if t['status'] == 'pending')
        
        if pending_minutes == 0:
            continue
            
        # Calculate weight
        priority_score = PROJECT_PRI_SCORE if project['priority'] else PROJECT_DEF_SCORE
        
        if project['deadline']:
            days_until = (datetime.strptime(project['deadline'], '%Y-%m-%d').date() - 
                         datetime.now().date()).days
            days_until = max(1, days_until)
        else:
            days_until = NO_DEADLINE_DAYS
            
        urgency_multiplier = exp(URGENCY_K / days_until)
        remaining_work_factor = pending_minutes / total_minutes if total_minutes > 0 else 1.0
        
        weight = priority_score * urgency_multiplier * remaining_work_factor
        
        buckets.append({
            'id': project['id'],
            'name': project['name'],
            'type': 'project',
            'weight': weight,
            'tasks': project_tasks,
            'allocated_minutes': 0
        })
    
    # Solo tier-2 bucket
    solo_tasks = [t for t in other_tasks if t['project_id'] is None]
    if solo_tasks:
        # Calculate individual weights for solo tasks
        solo_task_weights = []
        total_solo_weight = 0
        
        for task in solo_tasks:
            priority_score = SOLO_BUCKET_PRI if task['priority'] else SOLO_BUCKET_DEF
            
            if task['due_date']:
                days_until = (datetime.strptime(task['due_date'], '%Y-%m-%d').date() - 
                             datetime.now().date()).days
                days_until = max(1, days_until)
            else:
                days_until = NO_DEADLINE_DAYS
                
            urgency_multiplier = exp(URGENCY_K / days_until)
            task_weight = priority_score * urgency_multiplier
            
            solo_task_weights.append((task, task_weight))
            total_solo_weight += task_weight
        
        if total_solo_weight > 0:
            buckets.append({
                'id': SOLO_BUCKET_ID,
                'name': 'Solo Tasks',
                'type': 'solo',
                'weight': total_solo_weight / len(solo_tasks),  # Average weight
                'tasks': solo_tasks,
                'task_weights': solo_task_weights,
                'allocated_minutes': 0
            })
    
    if not buckets:
        return _format_plan_result(budget_minutes, scheduled_tasks)
    
    # Allocate budget proportionally
    total_weight = sum(b['weight'] for b in buckets)
    
    for bucket in buckets:
        if total_weight > 0:
            bucket['allocated_minutes'] = int(remaining_budget * (bucket['weight'] / total_weight))
        else:
            bucket['allocated_minutes'] = 0
    
    # Apply MIN_ALLOCATION floor
    eligible_buckets = [b for b in buckets if b['allocated_minutes'] >= MIN_ALLOCATION]
    
    if not eligible_buckets:
        # Fallback: give all to highest weight bucket
        highest_bucket = max(buckets, key=lambda b: b['weight'])
        highest_bucket['allocated_minutes'] = remaining_budget
        eligible_buckets = [highest_bucket]
    else:
        # Redistribute minutes from ineligible buckets
        ineligible_minutes = sum(b['allocated_minutes'] for b in buckets 
                               if b not in eligible_buckets)
        if ineligible_minutes > 0 and eligible_buckets:
            eligible_weight = sum(b['weight'] for b in eligible_buckets)
            for bucket in eligible_buckets:
                if eligible_weight > 0:
                    extra = int(ineligible_minutes * (bucket['weight'] / eligible_weight))
                    bucket['allocated_minutes'] += extra
    
    # STAGE 2: Select tasks within each bucket
    bucket_selections = []
    
    for bucket in eligible_buckets:
        if bucket['allocated_minutes'] <= 0:
            continue
            
        selected_tasks = []
        budget_left = bucket['allocated_minutes']
        
        if bucket['type'] == 'project':
            # Get milestones for ordering
            project_milestones = sorted(
                [m for m in milestones if m['project_id'] == bucket['id']], 
                key=lambda m: m['order']
            )
            
            # Group tasks by milestone
            milestone_tasks = {}
            no_milestone_tasks = []
            
            for task in bucket['tasks']:
                if task['status'] != 'pending':
                    continue
                    
                if task['milestone_id']:
                    if task['milestone_id'] not in milestone_tasks:
                        milestone_tasks[task['milestone_id']] = []
                    milestone_tasks[task['milestone_id']].append(task)
                else:
                    no_milestone_tasks.append(task)
            
            # Process tasks in milestone order
            for milestone in project_milestones:
                if milestone['id'] in milestone_tasks:
                    tasks_in_milestone = sorted(
                        milestone_tasks[milestone['id']], 
                        key=lambda t: (not t['priority'], t['order'])
                    )
                    
                    for task in tasks_in_milestone:
                        if budget_left <= 0:
                            break
                            
                        # Check dependencies
                        if task['depends_on_task']:
                            dep_scheduled = any(
                                st['task_id'] == task['depends_on_task'] 
                                for st in scheduled_tasks + selected_tasks
                            )
                            dep_completed = any(
                                t['id'] == task['depends_on_task'] and t['status'] == 'completed'
                                for t in tasks
                            )
                            if not (dep_scheduled or dep_completed):
                                continue
                        
                        estimate = task['estimated_minutes'] or DEFAULT_ESTIMATE
                        
                        if estimate <= budget_left:
                            scheduled_mins = estimate
                        elif budget_left >= PARTIAL_FLOOR:
                            scheduled_mins = budget_left
                        else:
                            continue
                        
                        selected_tasks.append({
                            'task': task,
                            'milestone_title': milestone['title'],
                            'scheduled_minutes': scheduled_mins,
                            'partial': scheduled_mins < estimate,
                            'carry_over_minutes': estimate - scheduled_mins
                        })
                        
                        budget_left -= scheduled_mins
            
            # Process no-milestone tasks
            no_milestone_sorted = sorted(
                no_milestone_tasks,
                key=lambda t: (not t['priority'], t['order'])
            )
            
            for task in no_milestone_sorted:
                if budget_left <= 0:
                    break
                    
                # Check dependencies
                if task['depends_on_task']:
                    dep_scheduled = any(
                        st['task_id'] == task['depends_on_task'] 
                        for st in scheduled_tasks + selected_tasks
                    )
                    dep_completed = any(
                        t['id'] == task['depends_on_task'] and t['status'] == 'completed'
                        for t in tasks
                    )
                    if not (dep_scheduled or dep_completed):
                        continue
                
                estimate = task['estimated_minutes'] or DEFAULT_ESTIMATE
                
                if estimate <= budget_left:
                    scheduled_mins = estimate
                elif budget_left >= PARTIAL_FLOOR:
                    scheduled_mins = budget_left
                else:
                    continue
                
                selected_tasks.append({
                    'task': task,
                    'milestone_title': None,
                    'scheduled_minutes': scheduled_mins,
                    'partial': scheduled_mins < estimate,
                    'carry_over_minutes': estimate - scheduled_mins
                })
                
                budget_left -= scheduled_mins
                
        else:  # solo bucket
            # Sort by individual weight
            sorted_tasks = sorted(
                bucket['task_weights'], 
                key=lambda tw: tw[1], 
                reverse=True
            )
            
            for task, _ in sorted_tasks:
                if budget_left <= 0:
                    break
                    
                # Check dependencies
                if task['depends_on_task']:
                    dep_scheduled = any(
                        st['task_id'] == task['depends_on_task'] 
                        for st in scheduled_tasks + selected_tasks
                    )
                    dep_completed = any(
                        t['id'] == task['depends_on_task'] and t['status'] == 'completed'
                        for t in tasks
                    )
                    if not (dep_scheduled or dep_completed):
                        continue
                
                estimate = task['estimated_minutes'] or DEFAULT_ESTIMATE
                
                if estimate <= budget_left:
                    scheduled_mins = estimate
                elif budget_left >= PARTIAL_FLOOR:
                    scheduled_mins = budget_left
                else:
                    continue
                
                selected_tasks.append({
                    'task': task,
                    'milestone_title': None,
                    'scheduled_minutes': scheduled_mins,
                    'partial': scheduled_mins < estimate,
                    'carry_over_minutes': estimate - scheduled_mins
                })
                
                budget_left -= scheduled_mins
        
        bucket_selections.append({
            'bucket': bucket,
            'selected_tasks': selected_tasks
        })
    
    # STAGE 3: Interleave project tasks round-robin by weight
    # Separate project and solo buckets
    project_buckets = []
    solo_bucket_tasks = []
    
    for selection in bucket_selections:
        if selection['bucket']['type'] == 'project':
            project_buckets.append({
                'bucket': selection['bucket'],
                'tasks': selection['selected_tasks'][:],  # Copy list
                'index': 0
            })
        else:
            solo_bucket_tasks.extend(selection['selected_tasks'])
    
    # Round-robin interleave
    interleaved_tasks = []
    
    while any(pb['index'] < len(pb['tasks']) for pb in project_buckets):
        # Sort by weight for this round
        active_buckets = [pb for pb in project_buckets if pb['index'] < len(pb['tasks'])]
        active_buckets.sort(key=lambda pb: pb['bucket']['weight'], reverse=True)
        
        for pb in active_buckets:
            if pb['index'] < len(pb['tasks']):
                interleaved_tasks.append(pb['tasks'][pb['index']])
                pb['index'] += 1
    
    # Add solo tasks at the end
    interleaved_tasks.extend(solo_bucket_tasks)
    
    # Convert to final format
    for task_info in interleaved_tasks:
        task = task_info['task']
        scheduled_tasks.append({
            'position': position,
            'task_id': task['id'],
            'project_id': task['project_id'],
            'is_solo': task['project_id'] is None,
            'tier1': False,
            'milestone_title': task_info['milestone_title'],
            'title': task['title'],
            'priority': task['priority'],
            'scheduled_minutes': task_info['scheduled_minutes'],
            'partial': task_info['partial'],
            'carry_over_minutes': task_info['carry_over_minutes']
        })
        position += 1
    
    return _format_plan_result(budget_minutes, scheduled_tasks)


def _format_plan_result(budget_minutes: int, scheduled_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Format the final plan result."""
    total_used = sum(t['scheduled_minutes'] for t in scheduled_tasks)
    
    return {
        'id': str(uuid4()),
        'budget_minutes': budget_minutes,
        'total_used_minutes': total_used,
        'slack_minutes': budget_minutes - total_used,
        'task_count': len(scheduled_tasks),
        'tasks': scheduled_tasks
    }
