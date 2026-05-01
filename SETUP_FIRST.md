# 🚀 INITIAL PUSH GUIDE — read this first, then delete it

This is your zip, Min. After you push, your teammates will add their folders.

## Step 1 — Create the GitHub repo

```bash
# unzip this folder somewhere, then:
cd personify
git init
git branch -M main
git add .
git commit -m "Initial skeleton: extension, docs, supabase schema"

# create a new repo on github.com (call it "personify")
# then connect and push:
git remote add origin git@github.com:<your-username>/personify.git
git push -u origin main
```

## Step 2 — Add your teammates as collaborators

On GitHub: **Settings → Collaborators → Add people**

Add:
- Daphne (Frontend)
- Yousif (Backend Core)
- Dev (ML Infra Backend)

## Step 3 — Send them their zips

- Send `daphne-frontend.zip` to Daphne
- Send `yousif-dev-backend.zip` to Yousif and Dev (they share the backend)

Each zip contains a `START_HERE.md` with their setup instructions.

## Step 4 — Set up Supabase (any one of you can do this)

1. Create a project at supabase.com (free tier)
2. SQL editor → paste the contents of `supabase/migrations/0001_initial.sql` → run
3. Share the project URL and anon key in your team chat — everyone needs it for their `.env` files

## Step 5 — Delete this file

```bash
rm SETUP_FIRST.md
git add -A && git commit -m "Remove setup guide"
git push
```

---

## Your role going forward

You own the **extension** (already in this repo) **and** the **AI pipeline** (lives inside the backend folder Yousif and Dev will push).

Your branches will look like:
- `mle/composite-selectors` (extension work)
- `mle/classify-prompt` (backend AI work — pair with Dev)
- `mle/generation-prompt` (backend AI work)
