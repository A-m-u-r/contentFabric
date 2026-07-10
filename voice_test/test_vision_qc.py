"""Live check of Gemini vision QC on cached clips with KNOWN defects.

broll_02 had a stranger woman at the fridge; avatar_05 shows a tablet with
garbled pseudo-text. If the reviewer flags both, item #6 works end-to-end.
Cheap Gemini flash calls only — no video generation.
"""
import os
import sys

sys.path.insert(0, "/app")

from app import get_user_api_key
from saasshorts import review_clip_quality

USER_ID = "b0dc0ca4-1538-4bb7-b2c5-88061c752ee1"
JOB = "/app/output/saas_e468baa0-3354-4d33-99f6-2763c7b21945"
SLUG = "not_your_fault_after_30"

gemini_key = get_user_api_key(USER_ID, "gemini")
assert gemini_key, "no gemini key in vault"

cases = [
    ("avatar_broll_02", {"visual_type": "broll"}),   # stranger woman expected
    ("avatar_05", {"visual_type": "talking"}),        # garbled tablet text expected
    ("avatar_01", {"visual_type": "talking"}),        # clean talking shot (control)
]
for name, shot in cases:
    clip = os.path.join(JOB, f"{SLUG}_{name}.mp4")
    review_json = f"{clip}.review.json"
    if os.path.exists(review_json):
        os.remove(review_json)  # force a fresh call for this test
    issues = review_clip_quality(clip, shot, gemini_key)
    print(f"{name}: {issues if issues else 'OK, дефектов нет'}")
