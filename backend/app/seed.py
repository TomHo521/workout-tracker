from .database import SessionLocal
from .models import Exercise

# name, muscle_group, equipment, contraindicated_for, sets, reps, notes, youtube search URL
EXERCISES = [
    ("Barbell Back Squat",      "legs",      "barbell",   ["lower_back","left_knee","right_knee"], 4, "5-8", "Compound. Heavy.",            "https://www.youtube.com/results?search_query=barbell+back+squat+form"),
    ("Goblet Squat",            "legs",      "dumbbell",  ["left_knee","right_knee"],              3, "8-12","Knee-friendlier squat.",      "https://www.youtube.com/results?search_query=goblet+squat+form"),
    ("Romanian Deadlift",       "legs",      "barbell",   ["lower_back"],                          3, "8-10","Hip hinge.",                  "https://www.youtube.com/results?search_query=romanian+deadlift+form"),
    ("Leg Press",               "legs",      "machine",   [],                                      3, "10-12","Machine compound.",           "https://www.youtube.com/results?search_query=leg+press+form"),
    ("Walking Lunge",           "legs",      "dumbbell",  ["left_knee","right_knee"],              3, "10/leg","Unilateral.",                "https://www.youtube.com/results?search_query=walking+lunge+form"),
    ("Leg Curl",                "legs",      "machine",   [],                                      3, "10-12","Hamstring isolation.",         "https://www.youtube.com/results?search_query=leg+curl+machine+form"),
    ("Bench Press",             "chest",     "barbell",   ["left_shoulder","right_shoulder"],      4, "5-8", "Compound.",                    "https://www.youtube.com/results?search_query=bench+press+form"),
    ("Dumbbell Bench Press",    "chest",     "dumbbell",  [],                                      3, "8-12","Shoulder-friendlier press.",   "https://www.youtube.com/results?search_query=dumbbell+bench+press+form"),
    ("Incline Dumbbell Press",  "chest",     "dumbbell",  [],                                      3, "8-12","Upper chest.",                 "https://www.youtube.com/results?search_query=incline+dumbbell+press+form"),
    ("Push-up",                 "chest",     "bodyweight",[],                                      3, "AMRAP","Scale on knees if needed.",    "https://www.youtube.com/results?search_query=pushup+form"),
    ("Pull-up",                 "back",      "bodyweight",["left_shoulder","right_shoulder"],      3, "5-10","Compound. Band-assist OK.",    "https://www.youtube.com/results?search_query=pullup+form"),
    ("Lat Pulldown",            "back",      "machine",   [],                                      3, "10-12","Vertical pull.",               "https://www.youtube.com/results?search_query=lat+pulldown+form"),
    ("Barbell Row",             "back",      "barbell",   ["lower_back"],                          3, "8-10","Horizontal pull.",             "https://www.youtube.com/results?search_query=barbell+row+form"),
    ("One-Arm DB Row",          "back",      "dumbbell",  [],                                      3, "10-12","Unilateral row.",              "https://www.youtube.com/results?search_query=one+arm+dumbbell+row+form"),
    ("Seated Cable Row",        "back",      "machine",   [],                                      3, "10-12","Back-friendly row.",           "https://www.youtube.com/results?search_query=seated+cable+row+form"),
    ("Overhead Press",          "shoulders", "barbell",   ["left_shoulder","right_shoulder"],      3, "5-8", "Compound press.",              "https://www.youtube.com/results?search_query=overhead+press+form"),
    ("Dumbbell Shoulder Press", "shoulders", "dumbbell",  [],                                      3, "8-12","Neutral grip friendly.",       "https://www.youtube.com/results?search_query=dumbbell+shoulder+press+form"),
    ("Lateral Raise",           "shoulders", "dumbbell",  [],                                      3, "12-15","Side delts.",                   "https://www.youtube.com/results?search_query=lateral+raise+form"),
    ("Face Pull",               "shoulders", "cable",     [],                                      3, "12-15","Rear delts/rotator cuff.",      "https://www.youtube.com/results?search_query=face+pull+form"),
    ("Barbell Curl",            "arms",      "barbell",   [],                                      3, "8-12","Biceps.",                      "https://www.youtube.com/results?search_query=barbell+curl+form"),
    ("Hammer Curl",             "arms",      "dumbbell",  [],                                      3, "10-12","Biceps/brachialis.",            "https://www.youtube.com/results?search_query=hammer+curl+form"),
    ("Triceps Pushdown",        "arms",      "cable",     [],                                      3, "10-12","Triceps isolation.",            "https://www.youtube.com/results?search_query=triceps+pushdown+form"),
    ("Overhead Triceps Ext.",   "arms",      "dumbbell",  [],                                      3, "10-12","Long head triceps.",            "https://www.youtube.com/results?search_query=overhead+triceps+extension+form"),
    ("Plank",                   "core",      "bodyweight",[],                                      3, "30-60s","Anti-extension.",              "https://www.youtube.com/results?search_query=plank+form"),
    ("Dead Bug",                "core",      "bodyweight",[],                                      3, "10/side","Back-friendly core.",           "https://www.youtube.com/results?search_query=dead+bug+exercise+form"),
    ("Hanging Knee Raise",      "core",      "bodyweight",["left_shoulder","right_shoulder"],      3, "8-12","Lower abs.",                   "https://www.youtube.com/results?search_query=hanging+knee+raise+form"),
    ("Back Extension",          "core",      "bodyweight",[],                                      3, "10-12","Low back / glutes.",            "https://www.youtube.com/results?search_query=back+extension+form"),
]


def seed_exercises():
    db = SessionLocal()
    try:
        existing = {e.name: e for e in db.query(Exercise).all()}
        for name, mg, eq, contra, sets, reps, notes, yt in EXERCISES:
            if name in existing:
                # backfill youtube_url if missing (older rows)
                if not existing[name].youtube_url:
                    existing[name].youtube_url = yt
                continue
            db.add(Exercise(
                name=name, muscle_group=mg, equipment=eq,
                contraindicated_for=contra, default_sets=sets,
                default_reps=reps, notes=notes, youtube_url=yt,
            ))
        db.commit()
    finally:
        db.close()
