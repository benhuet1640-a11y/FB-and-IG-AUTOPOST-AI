# Pipeline Reception — Social Autoposter

Posts to Facebook (and Instagram once it's enabled) **three times a day, every day**, New York time:

| Time | Post |
|---|---|
| 8am | Educational carousel: a hook cover, 5 teaching slides and a "Book a demo" slide at the end |
| 12pm | Single-image ad: headline, 3 benefits and a "Book a demo" button |
| 6pm | Educational carousel |

All posts are written for **plumbing business owners** nationwide. About 1 in 4 gets a **Pittsburgh** angle.

```
GitHub Actions (free cron)
   │
   ├─ autopost/generate.py  → Gemini (free) writes the post as JSON; OpenAI gpt-image-1-mini draws the artwork
   ├─ autopost/render.py    → adds all the text, logo and colors in code (no AI typos)
   ├─ git push              → images get a public URL (Instagram requires one)
   └─ autopost/publish.py   → Facebook post (+ Instagram carousel/image once enabled)
```

## Estimated cost (~90 posts/month)

| Part | Cost |
|---|---|
| GitHub Actions (public repo) | $0 |
| Meta Graph API (Facebook + Instagram) | $0 |
| Post text: Google Gemini free tier | $0 |
| Artwork: `gpt-image-1-mini`, medium quality, 1 image per post | ~$1.50/mo |
| **Total** | **≈ $1.50–2/month** |

For nicer art, set `image_model: gpt-image-1.5` (~$4.50/mo). For $0, set `cover_image: false`, which uses a plain branded background.

---

## One-time setup (~45 min)

### 1. Put this on GitHub
- Create a **public** repository on GitHub. Public is what keeps Actions free and gives the images a public URL. Your API keys stay private as Secrets.
- Upload this folder to it.

### 2. Get a free Gemini key (writes the posts)
- Go to https://aistudio.google.com/apikey → **Create API key**.

### 3. Get an OpenAI API key (draws the artwork)
**Your ChatGPT subscription doesn't cover this.** The API is billed separately and prepaid.
- Go to https://platform.openai.com → **Settings → Billing** and add $5 of credit. That lasts about 3 months. Leave auto-recharge off to cap your spending.
- Go to **Settings → Organization → General** and complete **Verify organization**. OpenAI requires this before you can use its image models.
- Go to **API keys → Create new secret key**.

### 4. Get your Meta credentials
1. Go to https://developers.facebook.com → **My Apps → Create App**. Choose **Business**, or "Other → Business" if asked.
2. In the app, add **Facebook Login for Business** and the **Instagram** product. You can leave the app in *Development* mode, because you're an admin posting to your own Page.
3. Open the **Graph API Explorer** (Tools menu):
   - Select your app, then **User Token**.
   - Add these permissions: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `business_management`, and for Instagram later, `instagram_basic` and `instagram_content_publish`.
   - Click **Generate Access Token** and approve.
4. Make the token long-lived: open the **Access Token Debugger** (Tools menu), paste the token, then click **Extend Access Token**. Copy the new token.
5. In Graph API Explorer, paste the long-lived token and run `GET me/accounts`. Find **Pipeline Reception** and copy:
   - its `id` → this is `FB_PAGE_ID`
   - its `access_token` → this is `META_PAGE_TOKEN`. This Page token doesn't expire.
6. *(When Instagram is out of review)* Run `GET {FB_PAGE_ID}?fields=instagram_business_account` and copy the id → this is `IG_USER_ID`.

### 5. Add the secrets to GitHub
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | from step 2 |
| `OPENAI_API_KEY` | from step 3 |
| `META_PAGE_TOKEN` | from step 4 |
| `FB_PAGE_ID` | from step 4 |
| `IG_USER_ID` | from step 4.6, once Instagram is ready |

Also check that **Settings → Actions → General → Workflow permissions** is set to **Read and write**.

### 6. Test it
- Go to **Actions → Auto-post → Run workflow**. Pick `carousel` or `ad` and leave "dry run" checked. This only generates images. Look in `posts/` to see them.
- Run it again with dry run **unchecked** to do a real post.
- After that it runs on its own.

### 7. When Instagram is back
1. Instagram app → Settings → **Account type and tools** → switch to a **Business** account, and link it to the Pipeline Reception Facebook Page.
2. Add the `IG_USER_ID` secret (step 4.6).
3. In `config.yaml`, set `platforms: instagram: true`.

---

## Customizing (all in `config.yaml` unless noted)

| Want to change… | Where |
|---|---|
| Features, claims rules, voice | `business` |
| Topics, Pittsburgh share, hashtags | `content` |
| Last carousel slide / button text | `cta` |
| Caption endings for each platform | `captions` |
| What posts at what time | `schedule.slots` (New York hours) |
| Art style, image model and quality | `ai.image_*` |
| The AI writing prompts themselves | `autopost/generate.py` → `CAROUSEL` / `AD` |

Preview the designs locally without any keys:
```bash
pip install -r requirements.txt
python -m autopost.main sample carousel
python -m autopost.main sample ad some-image.png   # with your own artwork
```

## Good to know
- **GitHub's schedule isn't exact.** Runs can start 5–30 minutes late.
- **If the artwork fails** (for example, OpenAI credit ran out), the post still goes out with the plain branded background.
- **History:** every published post is logged in `history.json`, and the AI avoids repeating recent topics.
- **When a run fails**, GitHub emails you.
- **Google may use free-tier Gemini prompts to improve its products.** That's fine here, since everything it writes gets posted publicly anyway.
- **Model names change over time.** If a run fails with "model not found", update the model names in `ai:`.
