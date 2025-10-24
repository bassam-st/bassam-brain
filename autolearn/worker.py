# autolearn/worker.py
from __future__ import annotations
from apscheduler.schedulers.blocking import BlockingScheduler
from pytz import timezone
from autolearn.learn_loop import run_once

def main():
    sched = BlockingScheduler(timezone=timezone("Asia/Aden"))
    # أول تشغيل عند الإقلاع
    sched.add_job(run_once, "date")
    # ثم كل 30 دقيقة
    sched.add_job(run_once, "cron", minute="*/30")
    print("✅ AutoLearn worker started (every 30 min)")
    sched.start()

if __name__ == "__main__":
    main()
