"""Knowledge the support chatbot is allowed to answer from."""

WELLLENS_KNOWLEDGE = """
WellLens — what it is and how it works (use only this to answer):

PRODUCT
- WellLens turns your own activity data (runs, rides, workouts) into plain-English
  wellbeing insights: trends, training load, and recovery signals.
- You upload or sync your own data — it isn't tied to one fitness platform.

UPLOADS & FILES
- Supported files: .fit, .gpx, .tcx (exported from most devices/apps).
- Go to the Upload page, choose files or drag them in, then "Upload & analyse".

INSIGHTS
- Per activity: distance, duration, average/max heart rate, pace, elevation.
- ACWR (acute:chronic workload ratio) flags overtraining risk: low / balanced /
  watch / high.
- Weekly distance, week-on-week change, and whether pace at a given heart rate is
  improving. A short AI summary explains what it means.

GARMIN
- You can connect a Garmin account to sync activities automatically (Connect Garmin
  on the dashboard), in addition to manual upload.

PLANS & PRICING
- Free: up to 5 uploads in total.
- Pro: £4.99 per month, gives UNLIMITED uploads. Upgrade from the Billing page.
- Manage or cancel anytime via the billing portal (Manage subscription).
- Payments are handled securely by Stripe; WellLens never sees your card details.

ACCOUNTS
- Sign up with email/password or "Continue with Google".
- It's an installable web app (PWA): "Add to Home Screen" on mobile.

PRIVACY
- Your activity data is yours; WellLens analyses it to produce your insights.
""".strip()
