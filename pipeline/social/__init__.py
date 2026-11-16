"""Instagram automation for @f1telemetryhub: pick a story per session, render a Reel and a
carousel, publish through the Instagram API with Instagram Login, then delete the video.

python -m pipeline.social run      [--session 2026_20_Q] [--dry-run] [--out ig_out]
python -m pipeline.social rewind   [--dry-run]       off season weekly post
python -m pipeline.social refresh                    refresh the long lived Instagram token
"""
