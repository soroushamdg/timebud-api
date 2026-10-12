"""
TimeBud — Session Planner
Schema v3: unified tasks table, UUID ids, UTC datetimes, new statuses.

Scheduling priority order
─────────────────────────
  TIER 1  Solo tasks where priority=True AND due_date is set
          → scheduled first, consume budget before anything else
          → sorted within tier by urgency (nearest deadline first)

  TIER 2  Everything else: projects (active only) + remaining solo tasks
          → weighted allocation:
             weight = project_priority_score × urgency_multiplier × remaining_work_factor
          → solo tasks without a project compete as their own bucket
"""

import math
import uuid
from datetime import date, datetime, timezone
from typing import Optional

# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────
URGENCY_K           = 3.5   # exponential urgency curve steepness
PROJECT_PRI_SCORE   = 2.0   # weight multiplier for priority=True project
PROJECT_DEF_SCORE   = 1.0   # weight multiplier for priority=False project
SOLO_BUCKET_PRI     = 2.0   # weight multiplier for solo bucket when any task is priority
SOLO_BUCKET_DEF     = 1.0
MIN_ALLOCATION      = 5    # skip a bucket if its allocation falls below this
PARTIAL_FLOOR       = 15    # only schedule a partial task if >= this many minutes remain
DEFAULT_ESTIMATE    = 25    # fallback estimated_minutes if missing
NO_DEADLINE_DAYS    = 30    # assumed days remaining for tasks/projects with no deadline
TODAY               = date(2026, 3, 4)   # pinned; in prod: date.today()

_id_counter = 200           # auto-increment for added tasks in the terminal demo


# ─────────────────────────────────────────────────────────────────────
# SEED DATA  — new schema
# ─────────────────────────────────────────────────────────────────────

# ── users ─────────────────────────────────────────────────────────────
USERS = [
    {
        "id": "user_clerk_abc123",   # clerk_id is the PK
        "email": "alex@example.com",
        "first_name": "Alex",
        "last_name": "Chen",
        "created_at": "2026-01-15T10:00:00Z",
    }
]

# ── projects ──────────────────────────────────────────────────────────
# status: active | paused | deleted | archived
# color:  optional hex string for display
PROJECTS = [
    {
        "id": "proj-001",
        "user_id": "user_clerk_abc123",
        "name": "Psychology Essay — Memory & Cognition",
        "description": "3000-word essay on working memory models",
        "deadline": "2026-03-07",          # stored UTC, displayed in local TZ
        "priority": True,
        "status": "active",
        "color": "#E07B7B",
        "created_at": "2026-02-20T09:00:00Z",
    },
    {
        "id": "proj-002",
        "user_id": "user_clerk_abc123",
        "name": "Personal Portfolio Website",
        "description": "NextJS portfolio with projects and contact form",
        "deadline": "2026-03-20",
        "priority": False,
        "status": "active",
        "color": "#7BB5E0",
        "created_at": "2026-02-22T11:00:00Z",
    },
    {
        "id": "proj-003",
        "user_id": "user_clerk_abc123",
        "name": "Intro to ML — Group Project",
        "description": "Classification model + written report",
        "deadline": "2026-03-14",
        "priority": True,
        "status": "active",
        "color": "#7BE09A",
        "created_at": "2026-02-18T08:00:00Z",
    },
]

# ── milestones ────────────────────────────────────────────────────────
MILESTONES = [
    # Essay milestones
    {"id": "ms-001", "project_id": "proj-001", "title": "Research & Outline",  "description": None, "target_date": "2026-03-05", "order": 1, "created_at": "2026-02-20T09:05:00Z"},
    {"id": "ms-002", "project_id": "proj-001", "title": "Write & Submit",       "description": None, "target_date": "2026-03-07", "order": 2, "created_at": "2026-02-20T09:05:00Z"},
    # Portfolio milestones
    {"id": "ms-003", "project_id": "proj-002", "title": "Design & Setup",       "description": None, "target_date": "2026-03-14", "order": 1, "created_at": "2026-02-22T11:05:00Z"},
    {"id": "ms-004", "project_id": "proj-002", "title": "Content & Deploy",     "description": None, "target_date": "2026-03-20", "order": 2, "created_at": "2026-02-22T11:05:00Z"},
    # ML milestones
    {"id": "ms-005", "project_id": "proj-003", "title": "Data Preparation",     "description": None, "target_date": "2026-03-10", "order": 1, "created_at": "2026-02-18T08:05:00Z"},
    {"id": "ms-006", "project_id": "proj-003", "title": "Model & Report",       "description": None, "target_date": "2026-03-14", "order": 2, "created_at": "2026-02-18T08:05:00Z"},
]

# ── tasks (unified table) ─────────────────────────────────────────────
# project_id   — None for solo tasks
# milestone_id — None for solo tasks or free-floating project tasks
# status       — "pending" | "completed"
# priority     — True | False
# due_date     — UTC date string or None
# depends_on_task — task id or None
TASKS = [
    # ── Essay / Research & Outline (ms-001) ──────────────────────────
    {"id": "t-001", "project_id": "proj-001", "milestone_id": "ms-001", "title": "Find 5 academic sources on working memory",               "description": None, "estimated_minutes": 30, "status": "pending", "due_date": None, "order": 1, "priority": False, "depends_on_task": None,    "created_at": "2026-02-20T09:10:00Z"},
    {"id": "t-002", "project_id": "proj-001", "milestone_id": "ms-001", "title": "Read and highlight key arguments from each source",        "description": None, "estimated_minutes": 45, "status": "pending", "due_date": None, "order": 2, "priority": False, "depends_on_task": "t-001", "created_at": "2026-02-20T09:10:00Z"},
    {"id": "t-003", "project_id": "proj-001", "milestone_id": "ms-001", "title": "Write outline with thesis and 3 supporting points",        "description": None, "estimated_minutes": 25, "status": "pending", "due_date": None, "order": 3, "priority": False, "depends_on_task": "t-002", "created_at": "2026-02-20T09:10:00Z"},
    # ── Essay / Write & Submit (ms-002) ──────────────────────────────
    {"id": "t-004", "project_id": "proj-001", "milestone_id": "ms-002", "title": "Write introduction and first body paragraph",              "description": None, "estimated_minutes": 40, "status": "pending", "due_date": None, "order": 1, "priority": False, "depends_on_task": "t-003", "created_at": "2026-02-20T09:10:00Z"},
    {"id": "t-005", "project_id": "proj-001", "milestone_id": "ms-002", "title": "Write second and third body paragraphs",                   "description": None, "estimated_minutes": 45, "status": "pending", "due_date": None, "order": 2, "priority": False, "depends_on_task": "t-004", "created_at": "2026-02-20T09:10:00Z"},
    {"id": "t-006", "project_id": "proj-001", "milestone_id": "ms-002", "title": "Write conclusion and format references (APA)",             "description": None, "estimated_minutes": 25, "status": "pending", "due_date": None, "order": 3, "priority": False, "depends_on_task": "t-005", "created_at": "2026-02-20T09:10:00Z"},
    {"id": "t-007", "project_id": "proj-001", "milestone_id": "ms-002", "title": "Proofread, fix grammar, submit on portal",                 "description": None, "estimated_minutes": 20, "status": "pending", "due_date": None, "order": 4, "priority": True,  "depends_on_task": "t-006", "created_at": "2026-02-20T09:10:00Z"},
    # ── Portfolio / Design & Setup (ms-003) ──────────────────────────
    {"id": "t-008", "project_id": "proj-002", "milestone_id": "ms-003", "title": "Pick a colour palette and typography on Coolors",          "description": None, "estimated_minutes": 15, "status": "pending", "due_date": None, "order": 1, "priority": False, "depends_on_task": None,    "created_at": "2026-02-22T11:10:00Z"},
    {"id": "t-009", "project_id": "proj-002", "milestone_id": "ms-003", "title": "Sketch wireframe of homepage layout",                      "description": None, "estimated_minutes": 20, "status": "pending", "due_date": None, "order": 2, "priority": False, "depends_on_task": "t-008", "created_at": "2026-02-22T11:10:00Z"},
    {"id": "t-010", "project_id": "proj-002", "milestone_id": "ms-003", "title": "Initialise NextJS project and push to GitHub",             "description": None, "estimated_minutes": 20, "status": "pending", "due_date": None, "order": 3, "priority": False, "depends_on_task": "t-009", "created_at": "2026-02-22T11:10:00Z"},
    {"id": "t-011", "project_id": "proj-002", "milestone_id": "ms-003", "title": "Build header, hero section, and footer with Tailwind",     "description": None, "estimated_minutes": 40, "status": "pending", "due_date": None, "order": 4, "priority": False, "depends_on_task": "t-010", "created_at": "2026-02-22T11:10:00Z"},
    # ── Portfolio / Content & Deploy (ms-004) ────────────────────────
    {"id": "t-012", "project_id": "proj-002", "milestone_id": "ms-004", "title": "Write About Me section and list 3 projects",               "description": None, "estimated_minutes": 30, "status": "pending", "due_date": None, "order": 1, "priority": False, "depends_on_task": "t-011", "created_at": "2026-02-22T11:10:00Z"},
    {"id": "t-013", "project_id": "proj-002", "milestone_id": "ms-004", "title": "Add contact form wired to email",                          "description": None, "estimated_minutes": 35, "status": "pending", "due_date": None, "order": 2, "priority": False, "depends_on_task": "t-012", "created_at": "2026-02-22T11:10:00Z"},
    {"id": "t-014", "project_id": "proj-002", "milestone_id": "ms-004", "title": "Deploy to Vercel and test on mobile",                      "description": None, "estimated_minutes": 15, "status": "pending", "due_date": None, "order": 3, "priority": False, "depends_on_task": "t-013", "created_at": "2026-02-22T11:10:00Z"},
    # ── ML / Data Preparation (ms-005) ───────────────────────────────
    {"id": "t-015", "project_id": "proj-003", "milestone_id": "ms-005", "title": "Download dataset and load into Jupyter notebook",          "description": None, "estimated_minutes": 15, "status": "pending", "due_date": None, "order": 1, "priority": False, "depends_on_task": None,    "created_at": "2026-02-18T08:10:00Z"},
    {"id": "t-016", "project_id": "proj-003", "milestone_id": "ms-005", "title": "Explore dataset — check for nulls, plot distributions",    "description": None, "estimated_minutes": 30, "status": "pending", "due_date": None, "order": 2, "priority": False, "depends_on_task": "t-015", "created_at": "2026-02-18T08:10:00Z"},
    {"id": "t-017", "project_id": "proj-003", "milestone_id": "ms-005", "title": "Clean data — handle missing values, encode categoricals",  "description": None, "estimated_minutes": 35, "status": "pending", "due_date": None, "order": 3, "priority": False, "depends_on_task": "t-016", "created_at": "2026-02-18T08:10:00Z"},
    {"id": "t-018", "project_id": "proj-003", "milestone_id": "ms-005", "title": "Split into train / val / test sets and save to CSV",       "description": None, "estimated_minutes": 15, "status": "pending", "due_date": None, "order": 4, "priority": False, "depends_on_task": "t-017", "created_at": "2026-02-18T08:10:00Z"},
    # ── ML / Model & Report (ms-006) ─────────────────────────────────
    {"id": "t-019", "project_id": "proj-003", "milestone_id": "ms-006", "title": "Train baseline model (logistic regression), log accuracy", "description": None, "estimated_minutes": 25, "status": "pending", "due_date": None, "order": 1, "priority": False, "depends_on_task": "t-018", "created_at": "2026-02-18T08:10:00Z"},
    {"id": "t-020", "project_id": "proj-003", "milestone_id": "ms-006", "title": "Train random forest, compare with baseline, pick best",   "description": None, "estimated_minutes": 35, "status": "pending", "due_date": None, "order": 2, "priority": False, "depends_on_task": "t-019", "created_at": "2026-02-18T08:10:00Z"},
    {"id": "t-021", "project_id": "proj-003", "milestone_id": "ms-006", "title": "Write results — tables, confusion matrix, commentary",    "description": None, "estimated_minutes": 40, "status": "pending", "due_date": None, "order": 3, "priority": True,  "depends_on_task": "t-020", "created_at": "2026-02-18T08:10:00Z"},
    # ── Solo tasks (no project_id, no milestone_id) ───────────────────
    {"id": "t-050", "project_id": None, "milestone_id": None, "title": "Email Prof. Martinez re: extension request",   "description": None, "estimated_minutes": 10, "status": "pending", "due_date": "2026-03-05", "order": 1, "priority": True,  "depends_on_task": None, "created_at": "2026-03-04T07:00:00Z"},
    {"id": "t-051", "project_id": None, "milestone_id": None, "title": "Read lecture slides for Thursday stats class", "description": None, "estimated_minutes": 25, "status": "pending", "due_date": "2026-03-06", "order": 2, "priority": False, "depends_on_task": None, "created_at": "2026-03-04T07:05:00Z"},
    {"id": "t-052", "project_id": None, "milestone_id": None, "title": "Back up laptop to external drive",             "description": None, "estimated_minutes": 15, "status": "pending", "due_date": None,         "order": 3, "priority": False, "depends_on_task": None, "created_at": "2026-03-04T07:10:00Z"},
]

# ── sessions (stored, not used by the planner logic — shown for schema reference) ──
SESSIONS: list[dict] = []


# ─────────────────────────────────────────────────────────────────────
# DATA VIEWS  — derive structured views from flat TASKS list
# ─────────────────────────────────────────────────────────────────────

def is_solo(task: dict) -> bool:
    return task["project_id"] is None and task["milestone_id"] is None


def is_tier1(task: dict) -> bool:
    """Tier 1: solo task with priority=True AND a due_date set."""
    return is_solo(task) and task["priority"] and task["due_date"] is not None


def pending_tasks_for_project(project_id: str, tasks: list[dict]) -> list[dict]:
    return [t for t in tasks if t["project_id"] == project_id and t["status"] == "pending"]


def pending_solo_tasks(tasks: list[dict]) -> list[dict]:
    return [t for t in tasks if is_solo(t) and t["status"] == "pending"]


def pending_tier1(tasks: list[dict]) -> list[dict]:
    return [t for t in tasks if is_tier1(t) and t["status"] == "pending"]


def pending_tier2_solo(tasks: list[dict]) -> list[dict]:
    """Solo tasks that are pending but NOT tier 1 (no priority+deadline combo)."""
    return [t for t in tasks if is_solo(t) and t["status"] == "pending" and not is_tier1(t)]


# ─────────────────────────────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────────────────────────────

def days_until(date_str: str) -> int:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return max(1, (d - TODAY).days)


def urgency_mult(days_remaining: int) -> float:
    return math.exp(URGENCY_K / days_remaining)


def project_pending_minutes(project_id: str, tasks: list[dict]) -> int:
    return sum(
        t.get("estimated_minutes", DEFAULT_ESTIMATE)
        for t in pending_tasks_for_project(project_id, tasks)
    )


def project_total_minutes(project_id: str, tasks: list[dict]) -> int:
    return sum(
        t.get("estimated_minutes", DEFAULT_ESTIMATE)
        for t in tasks
        if t["project_id"] == project_id
    )


def solo_pending_minutes(tasks: list[dict]) -> int:
    return sum(
        t.get("estimated_minutes", DEFAULT_ESTIMATE)
        for t in pending_tier2_solo(tasks)
    )


def solo_task_urgency_weight(task: dict) -> float:
    """Weight for sorting tier-2 solo tasks within their bucket."""
    pri     = SOLO_BUCKET_PRI if task["priority"] else SOLO_BUCKET_DEF
    days    = days_until(task["due_date"]) if task["due_date"] else NO_DEADLINE_DAYS
    return pri * urgency_mult(days)


def solo_bucket_weight(tasks: list[dict]) -> float:
    t2 = pending_tier2_solo(tasks)
    if not t2:
        return 0.0
    has_pri = any(t["priority"] for t in t2)
    pri     = SOLO_BUCKET_PRI if has_pri else SOLO_BUCKET_DEF
    min_due = min(
        (days_until(t["due_date"]) for t in t2 if t["due_date"]),
        default=NO_DEADLINE_DAYS
    )
    total_pending = sum(t.get("estimated_minutes", DEFAULT_ESTIMATE) for t in t2)
    total_all     = total_pending  # solo tasks have no "total", use pending as proxy
    rem_f         = 1.0            # always 1 — solo bucket hasn't started
    return pri * urgency_mult(min_due) * rem_f


# ─────────────────────────────────────────────────────────────────────
# STAGE 0 — Tier 1: schedule priority solo tasks with deadlines first
# ─────────────────────────────────────────────────────────────────────

def schedule_tier1(tasks: list[dict], budget_minutes: int) -> tuple[list[dict], int]:
    """
    Pull all tier-1 tasks (priority solo + has due_date), sorted by nearest deadline.
    Consume from the budget greedily. Return (scheduled_tasks, minutes_consumed).
    """
    tier1 = sorted(
        pending_tier1(tasks),
        key=lambda t: days_until(t["due_date"])   # nearest deadline first
    )
    if not tier1:
        return [], 0

    scheduled = []
    remaining = budget_minutes

    print(f"\n-- STAGE 0: Tier-1 Priority Tasks (scheduled before everything else) ----")
    print(f"  {'Task':<52} {'Est':>5} {'Due':>12}")
    print("  " + "-" * 69)
    for t in tier1:
        est = t.get("estimated_minutes", DEFAULT_ESTIMATE)
        due = t["due_date"]
        print(f"  {'[PRIO] ' + t['title']:<52} {est:>4}m  due {due}")

    for task in tier1:
        est = task.get("estimated_minutes", DEFAULT_ESTIMATE)
        if est <= remaining:
            scheduled.append({**task, "_scheduled_minutes": est, "_partial": False,
                               "_milestone_title": "Quick Tasks"})
            remaining -= est
        elif remaining >= PARTIAL_FLOOR:
            scheduled.append({**task, "_scheduled_minutes": remaining, "_partial": True,
                               "_remaining_after": est - remaining,
                               "_milestone_title": "Quick Tasks"})
            remaining = 0
            break
        # if < PARTIAL_FLOOR, skip this tier-1 task this session
        # (very small budgets — user will see it scheduled next session)

    consumed = budget_minutes - remaining
    if scheduled:
        print(f"\n  Scheduled {len(scheduled)} tier-1 task(s) consuming {consumed} min.")
        print(f"  Remaining budget for projects + other tasks: {remaining} min.")
    else:
        print(f"\n  No tier-1 tasks fit in this session (budget too small or none pending).")

    return scheduled, consumed


# ─────────────────────────────────────────────────────────────────────
# STAGE 1 — Allocate remaining budget across projects + tier-2 solo
# ─────────────────────────────────────────────────────────────────────

SOLO_BUCKET_ID = "__solo__"

def allocate_budget(projects: list[dict], tasks: list[dict], budget_minutes: int):
    active = [p for p in projects if p["status"] == "active"
              and project_pending_minutes(p["id"], tasks) > 0]
    has_solo = bool(pending_tier2_solo(tasks))

    # compute project weights
    weights = {}
    for p in active:
        days    = days_until(p["deadline"]) if p["deadline"] else NO_DEADLINE_DAYS
        pri     = PROJECT_PRI_SCORE if p["priority"] else PROJECT_DEF_SCORE
        urgency = urgency_mult(days)
        pending = project_pending_minutes(p["id"], tasks)
        total   = project_total_minutes(p["id"], tasks)
        rem_f   = pending / total if total > 0 else 0
        w       = pri * urgency * rem_f
        weights[p["id"]] = {
            "weight": w, "pending_minutes": pending, "project": p,
            "days": days, "priority": pri,
            "urgency": round(urgency, 2), "rem_f": round(rem_f, 3),
        }

    s_weight = solo_bucket_weight(tasks) if has_solo else 0.0

    # print weight table
    print(f"\n-- STAGE 1: Weight Calculation (remaining budget: {budget_minutes} min) -----")
    print(f"  {'Bucket':<47} {'Pri':>4} {'Urg':>6} {'RemF':>6} {'Weight':>7}")
    print("  " + "-" * 69)
    for pid, w in weights.items():
        col = w["project"].get("color", "")
        print(f"  {w['project']['name']:<47} {w['priority']:>4.1f} {w['urgency']:>6.2f} "
              f"{w['rem_f']:>6.3f} {w['weight']:>7.2f}  (due in {w['days']}d)")
    if has_solo:
        print(f"  {'[Quick Tasks — tier 2]':<47} {'--':>4} {'--':>6} {'--':>6} {s_weight:>7.2f}")

    if budget_minutes <= 0:
        print(f"\n  Budget exhausted by tier-1 tasks — skipping tier-2 allocation.")
        return {}, 0, weights, s_weight

    # proportional allocation
    total_w  = sum(v["weight"] for v in weights.values()) + s_weight
    raw      = {pid: (v["weight"] / total_w) * budget_minutes for pid, v in weights.items()} if total_w else {}
    raw_solo = (s_weight / total_w) * budget_minutes if (has_solo and total_w) else 0.0

    print(f"\n-- STAGE 1: Raw Allocations -----------------------------------------------")
    print(f"  {'Bucket':<47} {'Raw':>9} {'Pending':>8} {'Floor?':>7}")
    print("  " + "-" * 69)
    for pid, mins in raw.items():
        p    = weights[pid]["project"]
        pend = weights[pid]["pending_minutes"]
        fl   = "SKIP" if mins < MIN_ALLOCATION else "OK"
        print(f"  {p['name']:<47} {mins:>8.1f}m {pend:>7}m {fl:>7}")
    if has_solo:
        s_pend = solo_pending_minutes(tasks)
        fl     = "SKIP" if raw_solo < MIN_ALLOCATION else "OK"
        print(f"  {'[Quick Tasks — tier 2]':<47} {raw_solo:>8.1f}m {s_pend:>7}m {fl:>7}")

    # apply floor
    skipped  = {pid for pid, m in raw.items() if m < MIN_ALLOCATION}
    skip_s   = raw_solo < MIN_ALLOCATION
    included = {pid: v for pid, v in weights.items() if pid not in skipped}

    names = [weights[pid]["project"]["name"] for pid in skipped]
    if has_solo and skip_s: names.append("[Quick Tasks]")
    if names:
        print(f"\n  Skipped (below {MIN_ALLOCATION}-min floor): {', '.join(names)}")

    # ── FALLBACK: if the budget is too small to pass the floor for ANY bucket,
    #    give the entire budget to the single highest-weight bucket rather than
    #    refusing to schedule anything. A 35-min session should still work.
    if not included and (skip_s or not has_solo):
        best_pid = max(weights, key=lambda pid: weights[pid]["weight"])
        best     = weights[best_pid]
        print(f"\n  Budget too small to split — giving full {budget_minutes} min "
              f"to highest-weight bucket: {best['project']['name']}")
        final_proj = {best_pid: min(budget_minutes, best["pending_minutes"])}
        final_solo = 0
        final_proj = {pid: round(m) for pid, m in final_proj.items()}
        print(f"\n-- STAGE 1: Final Allocations ---------------------------------------------")
        for pid, mins in final_proj.items():
            print(f"  {weights[pid]['project']['name']:<47}  {mins:>3} min")
        return final_proj, final_solo, weights, s_weight

    # if solo bucket is the only one that passed the floor, give it the full budget
    if not included and has_solo and not skip_s:
        print(f"\n  Budget too small for projects — giving full {budget_minutes} min to Quick Tasks")
        final_proj = {}
        final_solo = min(budget_minutes, solo_pending_minutes(tasks))
        print(f"\n-- STAGE 1: Final Allocations ---------------------------------------------")
        print(f"  {'[Quick Tasks — tier 2]':<47}  {final_solo:>3} min")
        return final_proj, final_solo, weights, s_weight

    total_w2  = sum(v["weight"] for v in included.values()) + (s_weight if not skip_s and has_solo else 0)
    raw2      = {pid: (v["weight"] / total_w2) * budget_minutes for pid, v in included.items()} if total_w2 else {}
    raw_solo2 = ((s_weight / total_w2) * budget_minutes) if (not skip_s and has_solo and total_w2) else 0.0

    # cap at actual remaining work, redistribute surplus
    final_proj = {}
    surplus    = 0.0
    for pid, mins in raw2.items():
        cap = weights[pid]["pending_minutes"]
        if mins > cap:
            surplus += mins - cap
            final_proj[pid] = cap
            print(f"  Capped {weights[pid]['project']['name']} at {cap}m (only {cap}m of work left)")
        else:
            final_proj[pid] = mins

    solo_cap   = solo_pending_minutes(tasks)
    if raw_solo2 > solo_cap:
        surplus   += raw_solo2 - solo_cap
        final_solo = solo_cap
    else:
        final_solo = raw_solo2

    if surplus > 0.5:
        unc      = {pid: v for pid, v in included.items() if final_proj.get(pid, 0) < v["pending_minutes"]}
        solo_unc = not skip_s and has_solo and final_solo < solo_cap
        tw3      = sum(v["weight"] for v in unc.values()) + (s_weight if solo_unc else 0)
        if tw3 > 0:
            for pid in unc:
                final_proj[pid] = min(final_proj[pid] + (weights[pid]["weight"] / tw3) * surplus,
                                      weights[pid]["pending_minutes"])
            if solo_unc:
                final_solo = min(final_solo + (s_weight / tw3) * surplus, solo_cap)

    final_proj = {pid: round(m) for pid, m in final_proj.items()}
    final_solo = round(final_solo)

    print(f"\n-- STAGE 1: Final Allocations ---------------------------------------------")
    for pid, mins in final_proj.items():
        print(f"  {weights[pid]['project']['name']:<47}  {mins:>3} min")
    if has_solo and final_solo >= MIN_ALLOCATION:
        print(f"  {'[Quick Tasks — tier 2]':<47}  {final_solo:>3} min")

    return final_proj, final_solo, weights, s_weight


# ─────────────────────────────────────────────────────────────────────
# STAGE 2a — select project tasks (intra-session dependency unlock)
# ─────────────────────────────────────────────────────────────────────

def select_project_tasks(project_id: str, tasks: list[dict], allocation: int,
                         milestones: list[dict]) -> tuple[list[dict], int]:
    """
    Select pending project tasks in milestone-order → task-order.
    Unlocks depends_on_task within the same session as tasks are fully scheduled.
    Tasks with priority=True are surfaced first within their eligible set.
    """
    all_proj_tasks = {t["id"]: t for t in tasks if t["project_id"] == project_id}
    satisfied      = {t["id"] for t in all_proj_tasks.values() if t["status"] == "completed"}

    # build milestone lookup for ordering
    ms_order = {ms["id"]: ms["order"] for ms in milestones if ms["project_id"] == project_id}

    def task_sort_key(t):
        ms_ord  = ms_order.get(t["milestone_id"], 999) if t["milestone_id"] else 999
        return (ms_ord, t.get("order", 999))

    def milestone_title_for(t):
        if not t["milestone_id"]:
            return "No Milestone"
        ms = next((m for m in milestones if m["id"] == t["milestone_id"]), None)
        return ms["title"] if ms else "Unknown Milestone"

    ordered = sorted(
        [t for t in all_proj_tasks.values() if t["status"] == "pending"],
        key=task_sort_key
    )

    scheduled     = []
    remaining     = allocation
    scheduled_ids = set()

    added = True
    while added and remaining > 0:
        added = False

        # within each pass, try priority tasks first, then normal
        for priority_first in [True, False]:
            for task in ordered:
                if task["id"] in scheduled_ids:
                    continue
                if task["priority"] != priority_first:
                    continue
                dep = task.get("depends_on_task")
                if dep and dep not in satisfied:
                    continue
                est = task.get("estimated_minutes", DEFAULT_ESTIMATE)
                if est <= remaining:
                    scheduled.append({**task,
                                       "_scheduled_minutes": est,
                                       "_partial": False,
                                       "_milestone_title": milestone_title_for(task)})
                    satisfied.add(task["id"])
                    scheduled_ids.add(task["id"])
                    remaining -= est
                    added = True
                elif remaining >= PARTIAL_FLOOR and task["id"] not in scheduled_ids:
                    scheduled.append({**task,
                                       "_scheduled_minutes": remaining,
                                       "_partial": True,
                                       "_remaining_after": est - remaining,
                                       "_milestone_title": milestone_title_for(task)})
                    scheduled_ids.add(task["id"])
                    remaining = 0
                    added = False
                    break
            if remaining == 0:
                break

    return scheduled, allocation - remaining


# ─────────────────────────────────────────────────────────────────────
# STAGE 2b — select tier-2 solo tasks sorted by urgency weight
# ─────────────────────────────────────────────────────────────────────

def select_solo_tasks(tasks: list[dict], allocation: int) -> tuple[list[dict], int]:
    pending   = sorted(pending_tier2_solo(tasks), key=solo_task_urgency_weight, reverse=True)
    scheduled = []
    remaining = allocation

    for task in pending:
        est = task.get("estimated_minutes", DEFAULT_ESTIMATE)
        if est <= remaining:
            scheduled.append({**task, "_scheduled_minutes": est, "_partial": False,
                               "_milestone_title": "Quick Tasks"})
            remaining -= est
        elif remaining >= PARTIAL_FLOOR:
            scheduled.append({**task, "_scheduled_minutes": remaining, "_partial": True,
                               "_remaining_after": est - remaining,
                               "_milestone_title": "Quick Tasks"})
            remaining = 0
            break

    return scheduled, allocation - remaining


# ─────────────────────────────────────────────────────────────────────
# STAGE 3 — interleave (round-robin by weight)
# ─────────────────────────────────────────────────────────────────────

def interleave(project_tasks: dict, solo_scheduled: list[dict],
               weights: dict, solo_weight: float) -> list[dict]:
    buckets = [(pid, weights[pid]["weight"], list(t)) for pid, t in project_tasks.items()]
    if solo_scheduled:
        buckets.append((SOLO_BUCKET_ID, solo_weight, list(solo_scheduled)))
    buckets.sort(key=lambda b: b[1], reverse=True)
    queues  = {b[0]: b[2] for b in buckets}
    order   = [b[0] for b in buckets]
    result  = []
    while any(queues[bid] for bid in order):
        for bid in order:
            if queues[bid]:
                result.append(queues[bid].pop(0))
    return result


# ─────────────────────────────────────────────────────────────────────
# PLAN SESSION
# ─────────────────────────────────────────────────────────────────────

def plan_session(projects: list[dict], milestones: list[dict],
                 tasks: list[dict], budget_minutes: int) -> dict:
    print(f"\n{'='*72}")
    print(f"  TIMEBUD SESSION PLANNER  |  {TODAY}  |  Budget: {budget_minutes} min")
    print(f"{'='*72}")

    # ── Stage 0: tier-1 tasks first ──────────────────────────────────
    tier1_scheduled, tier1_consumed = schedule_tier1(tasks, budget_minutes)
    remaining_budget = budget_minutes - tier1_consumed

    # ── Stage 1: allocate remaining budget ───────────────────────────
    proj_alloc, solo_alloc, weights, solo_weight = allocate_budget(
        projects, tasks, remaining_budget
    )

    # ── Stage 2: select tasks ────────────────────────────────────────
    print(f"\n-- STAGE 2: Task Selection ------------------------------------------------")
    project_tasks = {}
    project_used  = {}

    for pid, alloc in proj_alloc.items():
        t_selected, used = select_project_tasks(pid, tasks, alloc, milestones)
        project_tasks[pid] = t_selected
        project_used[pid]  = used
        proj = next(p for p in projects if p["id"] == pid)
        print(f"\n  {proj['name']}  (allocated {alloc} min, using {used} min):")
        for t in t_selected:
            pri  = "[*] " if t["priority"] else "    "
            note = (f"  <- PARTIAL ({t['_scheduled_minutes']} of "
                    f"{t.get('estimated_minutes', DEFAULT_ESTIMATE)} min, "
                    f"{t['_remaining_after']} min carry over)") if t["_partial"] else ""
            print(f"    {pri}[{t['_scheduled_minutes']:>2}m]  {t['title']}{note}")

    solo_scheduled = []
    solo_used      = 0
    if solo_alloc >= MIN_ALLOCATION and pending_tier2_solo(tasks):
        solo_scheduled, solo_used = select_solo_tasks(tasks, solo_alloc)
        print(f"\n  [Quick Tasks — tier 2]  (allocated {solo_alloc} min, using {solo_used} min):")
        for t in solo_scheduled:
            pri  = "[*] " if t["priority"] else "    "
            due  = f"  [due {t['due_date']}]" if t.get("due_date") else ""
            note = (f"  <- PARTIAL ({t['_scheduled_minutes']} of "
                    f"{t.get('estimated_minutes', DEFAULT_ESTIMATE)} min, "
                    f"{t['_remaining_after']} min carry over)") if t["_partial"] else ""
            print(f"    {pri}[{t['_scheduled_minutes']:>2}m]  {t['title']}{due}{note}")

    # ── Stage 3: build final list ────────────────────────────────────
    # Tier-1 tasks go first. Then interleaved tier-2.
    tier2_interleaved = interleave(project_tasks, solo_scheduled, weights, solo_weight)
    all_tasks_ordered = tier1_scheduled + tier2_interleaved

    total_used = tier1_consumed + sum(project_used.values()) + solo_used
    slack      = budget_minutes - total_used

    # map task id -> project id for output
    task_to_proj = {t["id"]: pid for pid, ts in project_tasks.items() for t in ts}

    session = {
        "id":                 str(uuid.uuid4()),
        "budget_minutes":     budget_minutes,
        "total_used_minutes": total_used,
        "slack_minutes":      slack,
        "task_count":         len(all_tasks_ordered),
        "tasks":              [],
    }

    for i, t in enumerate(all_tasks_ordered):
        is_tier1_task = t["id"] in {x["id"] for x in tier1_scheduled}
        pid = task_to_proj.get(t["id"], SOLO_BUCKET_ID)
        session["tasks"].append({
            "position":           i + 1,
            "task_id":            t["id"],
            "project_id":         pid,
            "is_solo":            is_solo(t),
            "tier1":              is_tier1_task,
            "milestone_title":    t.get("_milestone_title", ""),
            "title":              t["title"],
            "priority":           t["priority"],
            "scheduled_minutes":  t["_scheduled_minutes"],
            "partial":            t["_partial"],
            "carry_over_minutes": t.get("_remaining_after", 0),
        })

    return session


# ─────────────────────────────────────────────────────────────────────
# APPLY SESSION
# ─────────────────────────────────────────────────────────────────────

def apply_session(tasks: list[dict], session: dict) -> None:
    lookup = {t["id"]: t for t in tasks}
    for s in session["tasks"]:
        task = lookup.get(s["task_id"])
        if not task:
            continue
        if s["partial"]:
            task["estimated_minutes"] = s["carry_over_minutes"]
        else:
            task["status"] = "completed"


# ─────────────────────────────────────────────────────────────────────
# COMPLETION
# ─────────────────────────────────────────────────────────────────────

def everything_done(projects: list[dict], tasks: list[dict]) -> bool:
    proj_done = all(
        t["status"] == "completed"
        for t in tasks if t["project_id"] is not None
    )
    solo_done = all(
        t["status"] == "completed"
        for t in tasks if is_solo(t)
    )
    return proj_done and solo_done


# ─────────────────────────────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────────────────────────────

def print_status(projects: list[dict], milestones: list[dict], tasks: list[dict]) -> None:
    print("\n  Projects:")
    for p in projects:
        if p["status"] in ("deleted",):
            continue
        if p["status"] == "paused":
            flag = "[~~]"
        else:
            pending = project_pending_minutes(p["id"], tasks)
            done_c  = sum(1 for t in tasks if t["project_id"] == p["id"] and t["status"] == "completed")
            total_c = sum(1 for t in tasks if t["project_id"] == p["id"])
            days    = days_until(p["deadline"]) if p["deadline"] else None
            flag    = "[!!]" if (days and days <= 2) else "[! ]" if (days and days <= 7) else "[ ]"
            pri     = "*" if p["priority"] else " "
            day_str = f"due in {days}d" if days else "no deadline"
            status_tag = "" if p["status"] == "active" else f" [{p['status'].upper()}]"
            print(f"    {flag} {pri} {p['name']:<45}  {done_c}/{total_c} tasks  "
                  f"{pending}m left  {day_str}{status_tag}")

    solo_pend = pending_solo_tasks(tasks)
    solo_done = [t for t in tasks if is_solo(t) and t["status"] == "completed"]
    if tasks:
        t1_pend = [t for t in solo_pend if is_tier1(t)]
        t2_pend = [t for t in solo_pend if not is_tier1(t)]
        print(f"\n  Quick Tasks:  ({len(solo_pend)} pending / {len(solo_done)} done)")
        if t1_pend:
            print(f"  [TIER 1 — scheduled first]")
            for t in sorted(t1_pend, key=lambda x: days_until(x["due_date"])):
                est = t.get("estimated_minutes", DEFAULT_ESTIMATE)
                print(f"    [    ] [*] {t['title']:<50}  [{est}m]  due {t['due_date']}")
        if t2_pend:
            print(f"  [TIER 2 — weighted with projects]")
            for t in t2_pend:
                est = t.get("estimated_minutes", DEFAULT_ESTIMATE)
                pri = "[*]" if t["priority"] else "   "
                due = f"  due {t['due_date']}" if t["due_date"] else ""
                print(f"    [    ] {pri} {t['title']:<50}  [{est}m]{due}")
        for t in solo_done:
            print(f"    [done]     {t['title']}")


def print_session_plan(session: dict, projects: list[dict]) -> None:
    print(f"\n{'='*72}")
    print(f"  SESSION {session['session_number']} PLAN  --  {session['budget_minutes']} min budget")
    print(f"{'='*72}")
    print(f"  Tasks: {session['task_count']}   "
          f"Used: {session['total_used_minutes']} min   "
          f"Slack: {session['slack_minutes']} min\n")

    prev_tier = None
    for t in session["tasks"]:
        cur_tier = "tier1" if t["tier1"] else "tier2"
        if cur_tier != prev_tier:
            if cur_tier == "tier1":
                print(f"  --- Priority Quick Tasks (do these first) ---")
            else:
                print(f"  --- Project Work + Other Tasks ---")
            prev_tier = cur_tier

        if t["is_solo"]:
            label = "[Quick Task]   "
        else:
            proj  = next((p for p in projects if p["id"] == t["project_id"]), None)
            label = f"[{proj['name'][:28]}]" if proj else "[Unknown]      "
        pri  = "[*]" if t["priority"] else "   "
        note = (f"  <- partial ({t['carry_over_minutes']} min carries over)"
                if t["partial"] else "")
        print(f"  {t['position']:>2}.  {label:<31}  {pri}  [{t['scheduled_minutes']:>2}m]  "
              f"{t['title']}{note}")

    print(f"\n  Total: {session['total_used_minutes']} / {session['budget_minutes']} min")


def print_completion(projects: list[dict], tasks: list[dict], session_log: list[dict]) -> None:
    total_min  = sum(s["total_used_minutes"] for s in session_log)
    hours, rem = divmod(total_min, 60)
    print(f"\n{'='*72}")
    print(f"  ALL DONE!")
    print(f"{'='*72}")
    print(f"\n  Sessions:         {len(session_log)}")
    print(f"  Total time worked: {hours}h {rem}m\n")
    for p in projects:
        total = sum(1 for t in tasks if t["project_id"] == p["id"])
        print(f"  [x] {p['name']}  ({total} tasks)")
    done_solo = [t for t in tasks if is_solo(t) and t["status"] == "completed"]
    if done_solo:
        print(f"\n  Quick Tasks completed:  ({len(done_solo)})")
        for t in done_solo:
            print(f"  [x] {t['title']}")
    print(f"\n  Session breakdown:")
    for i, s in enumerate(session_log, 1):
        print(f"    Session {i}:  {s['budget_minutes']} min budget  ->  "
              f"{s['total_used_minutes']} min used  ({s['task_count']} tasks)")
    print()


# ─────────────────────────────────────────────────────────────────────
# SOLO TASK MANAGEMENT
# ─────────────────────────────────────────────────────────────────────

def prompt_add_task(tasks: list[dict]) -> None:
    global _id_counter
    print("\n  -- Add Quick Task -------------------------------------------------------")
    title = input("  Title: ").strip()
    if not title:
        print("  Cancelled.")
        return

    while True:
        try:
            raw = input(f"  Estimated minutes [{DEFAULT_ESTIMATE}]: ").strip()
            est = int(raw) if raw else DEFAULT_ESTIMATE
            if est < 1: raise ValueError
            break
        except ValueError:
            print("  Enter a whole number > 0.")

    pri_raw  = input("  Priority? [y/n]: ").strip().lower()
    priority = pri_raw == "y"

    due_raw  = input("  Due date (YYYY-MM-DD) or blank: ").strip()
    due_date = None
    if due_raw:
        try:
            datetime.strptime(due_raw, "%Y-%m-%d")
            due_date = due_raw
        except ValueError:
            print("  Invalid date — saving without due date.")

    tier = "TIER 1" if (priority and due_date) else "TIER 2"
    tasks.append({
        "id":                f"t-{_id_counter:03d}",
        "project_id":        None,
        "milestone_id":      None,
        "title":             title,
        "description":       None,
        "estimated_minutes": est,
        "status":            "pending",
        "due_date":          due_date,
        "order":             len(tasks) + 1,
        "priority":          priority,
        "depends_on_task":   None,
        "created_at":        datetime.now(timezone.utc).isoformat(),
    })
    _id_counter += 1
    print(f"  Added [{tier}]: '{title}'  [{est}m  {'priority' if priority else 'normal'}"
          f"{'  due ' + due_date if due_date else ''}]")


def prompt_delete_task(tasks: list[dict]) -> None:
    pending = [t for t in tasks if is_solo(t) and t["status"] == "pending"]
    if not pending:
        print("\n  No pending quick tasks to delete.")
        return
    print("\n  -- Delete Quick Task ----------------------------------------------------")
    for i, t in enumerate(pending, 1):
        due = f"  due {t['due_date']}" if t["due_date"] else ""
        pri = "[*] " if t["priority"] else "    "
        print(f"  {i}.  {pri}{t['title']}  [{t.get('estimated_minutes', DEFAULT_ESTIMATE)}m]{due}")
    while True:
        try:
            idx = int(input("  Number to delete (0 to cancel): ").strip())
            if idx == 0:
                print("  Cancelled.")
                return
            if 1 <= idx <= len(pending):
                break
            raise ValueError
        except ValueError:
            print(f"  Enter 0–{len(pending)}.")
    t = pending[idx - 1]
    tasks.remove(t)
    print(f"  Deleted: '{t['title']}'")


def prompt_mark_done(tasks: list[dict]) -> None:
    pending = [t for t in tasks if is_solo(t) and t["status"] == "pending"]
    if not pending:
        print("\n  No pending quick tasks.")
        return
    print("\n  -- Mark Quick Task Done -------------------------------------------------")
    for i, t in enumerate(pending, 1):
        due = f"  due {t['due_date']}" if t["due_date"] else ""
        pri = "[*] " if t["priority"] else "    "
        print(f"  {i}.  {pri}{t['title']}  [{t.get('estimated_minutes', DEFAULT_ESTIMATE)}m]{due}")
    while True:
        try:
            idx = int(input("  Mark number done (0 to cancel): ").strip())
            if idx == 0:
                print("  Cancelled.")
                return
            if 1 <= idx <= len(pending):
                break
            raise ValueError
        except ValueError:
            print(f"  Enter 0–{len(pending)}.")
    t = pending[idx - 1]
    t["status"] = "completed"
    print(f"  Done: '{t['title']}'")


# ─────────────────────────────────────────────────────────────────────
# INTERACTIVE LOOP
# ─────────────────────────────────────────────────────────────────────

def run_interactive(projects: list[dict], milestones: list[dict], tasks: list[dict]) -> None:
    session_number = 0
    session_log    = []

    print(f"\n{'='*72}")
    print(f"  TIMEBUD  --  Session Planner")
    print(f"  {len(projects)} projects  |  "
          f"{len([t for t in tasks if not is_solo(t)])} project tasks  |  "
          f"{len([t for t in tasks if is_solo(t)])} quick tasks")
    print(f"  Scheduling rule: priority quick tasks with deadlines go first (Tier 1)")
    print(f"{'='*72}")

    while not everything_done(projects, tasks):
        print_status(projects, milestones, tasks)
        print(f"""
  Options:
    [s]  Start a session
    [a]  Add a quick task
    [d]  Delete a quick task
    [m]  Mark a quick task done manually
    [q]  Quit""")

        choice = input("\n  -> ").strip().lower()

        if choice == "q":
            print("\n  Goodbye.\n")
            break
        elif choice == "a":
            prompt_add_task(tasks)
        elif choice == "d":
            prompt_delete_task(tasks)
        elif choice == "m":
            prompt_mark_done(tasks)
        elif choice == "s":
            print()
            while True:
                try:
                    raw    = input("  How many minutes can you work? -> ").strip()
                    budget = int(raw)
                    if budget < 1: raise ValueError
                    break
                except ValueError:
                    print("  Enter a whole number > 0.")

            session_number += 1
            session  = plan_session(projects, milestones, tasks, budget)
            session["session_number"] = session_number

            if session["task_count"] == 0:
                print(f"\n  No tasks fit in {budget} min. "
                      f"Minimum schedulable unit is {PARTIAL_FLOOR} min.\n")
                session_number -= 1
                continue

            print_session_plan(session, projects)
            session_log.append(session)

            print()
            confirm = input("  Mark these tasks as done and move on? [y/n] -> ").strip().lower()
            if confirm != "y":
                print("  Session discarded — nothing updated.\n")
                session_log.pop()
                session_number -= 1
                continue

            apply_session(tasks, session)

            # store session record
            SESSIONS.append({
                "id":             session["id"],
                "user_id":        USERS[0]["id"],
                "start_time":     datetime.now(timezone.utc).isoformat(),
                "end_time":       datetime.now(timezone.utc).isoformat(),
                "budget_minutes": session["budget_minutes"],
                "tasks_list":     [t["task_id"] for t in session["tasks"]],
            })

            print(f"\n  Session {session_number} applied.\n")
        else:
            print("  Unknown option — enter s, a, d, m, or q.")

    if everything_done(projects, tasks):
        print_completion(projects, tasks, session_log)


# ─────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_interactive(PROJECTS, MILESTONES, TASKS)