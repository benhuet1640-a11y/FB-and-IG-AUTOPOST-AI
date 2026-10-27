# Social Autoposter

Two or three times a day, this runs in the cloud and:

1. **Writes** a new educational carousel with AI (Google Gemini free tier). It checks your posting history so topics don't repeat.
2. **Designs** branded 1080×1350 slides: a cover hook, 5 teaching slides, and a CTA slide at the end.
3. **Posts** the carousel to **Instagram** and **Facebook** through Meta's free official API.

**Cost: $0.** GitHub Actions is free for public repos, the Gemini API has a free tier, and the Meta Graph API is free.

```
GitHub Actions (cron, 2–3×/day)
   │
   ├─ autopost/generate.py  → Gemini writes topic, slides, caption (JSON)
   ├─ autopost/render.py    → Pillow draws slide_01.jpg … slide_07.jpg
   ├─ git push              → images get a public URL (Instagram requires one)
   └─ autopost/publish.py   → Instagram carousel + Facebook multi-photo post
```

---

## One-time setup (~45 min)

### 1. Put this on GitHub
- Create a **public** repository on GitHub. Public is what keeps Actions free and gives the images a public URL. Your API keys stay private as Secrets.
- Upload this folder to it.

### 2. Get a free Gemini API key
- Go to https://aistudio.google.com/apikey and click **Create API key**.
- Save it as the GitHub secret `GEMINI_API_KEY` (see step 4).

### 3. Get your Meta credentials
**Requirements:** your Instagram must be a **Business or Creator** account, and it must be **linked to your Facebook Page** (Instagram app → Settings → Account type and tools / Linked accounts).

1. Go to https://developers.facebook.com → **My Apps → Create App**. Choose **Business**, or "Other → Business" if asked.
2. In the app, add the **Instagram** product and **Facebook Login for Business**. You can leave the app in *Development* mode, because you're an admin posting to your own accounts.
3. Open the **Graph API Explorer** (Tools menu):
   - Select your app, then **User Token**.
   - Add these permissions: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`, `instagram_content_publish`, `business_management`.
   - Click **Generate Access Token** and approve.
4. Make the token long-lived: open the **Access Token Debugger** (Tools menu), paste the token, then click **Extend Access Token** at the bottom. Copy the new token.
5. Back in Graph API Explorer, paste the long-lived token and run:
   - `GET me/accounts` → find your Page and copy its **`id`** (this is `FB_PAGE_ID`) and its **`access_token`** (this is `META_PAGE_TOKEN`). A Page token made from a long-lived user token **doesn't expire**.
   - `GET {FB_PAGE_ID}?fields=instagram_business_account` → copy the id. This is `IG_USER_ID`.

### 4. Add the secrets to GitHub
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | from step 2 |
| `META_PAGE_TOKEN` | Page access token from step 3 |
| `FB_PAGE_ID` | Page id from step 3 |
| `IG_USER_ID` | Instagram business account id from step 3 |

Also check that **Settings → Actions → General → Workflow permissions** is set to **Read and write**.

### 5. Test it
- Go to **Actions → Auto-post carousel → Run workflow**, and leave "dry run" checked. This only generates slides. Look in `posts/` to see them.
- Run it again with dry run **unchecked** to do a real post.
- After that it runs on its own on the schedule.

---

## Customizing

| Want to change… | Edit |
|---|---|
| Topics, audience, tone, number of slides | `config.yaml` → `content` |
| Brand colors, @handle | `config.yaml` → `brand` |
| Last-slide CTA text | `config.yaml` → `cta` |
| The AI prompt itself | `autopost/generate.py` → `PROMPT` |
| Posting times / 2× vs 3× a day | `.github/workflows/post.yml` → `cron` lines (times are UTC) |
| Post to only IG or only FB | `config.yaml` → `platforms` |
| Use OpenAI instead of Gemini | `config.yaml` → `ai.provider: openai`, and add the `OPENAI_API_KEY` secret (about $0.10/month at this volume) |

Preview locally without any keys:
```bash
pip install -r requirements.txt
python -m autopost.main sample      # renders slides into posts/<timestamp>/
```

## Good to know
- **GitHub's schedule isn't exact.** Runs can start 5–30 minutes late. That's fine for social posts.
- **Gemini model names change over time.** If generation starts failing with a "model not found" error, update `ai.gemini_model` in `config.yaml` to the current Flash model listed at https://ai.google.dev/gemini-api/docs/models.
- **History:** every published post is logged in `history.json`, and the AI is told to avoid the last 60 topics.
- If one platform fails, the other still posts. The run is marked failed, and GitHub emails you.
- Instagram allows up to 100 API posts per day, so 3 a day is no problem.
