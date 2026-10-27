# Pipeline Reception — Social Autoposter

Three times a day (8am, noon and 6pm New York time), this runs in the cloud and:

1. **Writes** a new educational carousel with ChatGPT (OpenAI API): a hook, 5 teaching slides and a caption with hashtags. It checks posting history so topics don't repeat.
2. **Draws** a custom cover illustration with ChatGPT's image model. This is the hybrid approach: the AI makes the artwork, and the code adds the text so it's always spelled right and on-brand.
3. **Designs** branded 1080×1350 slides using your logo and colors. The CTA appears only on the last slide.
4. **Posts** the carousel to **Instagram** and **Facebook** through Meta's free official API.

```
GitHub Actions (free cron)
   │
   ├─ autopost/generate.py  → gpt-5-mini writes the post (JSON) + gpt-image-1.5 draws the cover art
   ├─ autopost/render.py    → Pillow builds slide_01.jpg … slide_07.jpg with logo, colors and text
   ├─ git push              → images get a public URL (Instagram requires one)
   └─ autopost/publish.py   → Instagram carousel + Facebook multi-photo post
```

## Estimated cost at 3 posts a day (~90 posts/month)

| Part | Cost |
|---|---|
| GitHub Actions (public repo) | $0 |
| Meta Graph API (Instagram + Facebook) | $0 |
| Post text: `gpt-5-mini` | ~$0.50/mo |
| Cover image: `gpt-image-1.5` medium, 1 per post | ~$4.50/mo |
| **Total** | **≈ $5/month** |

To spend less, set `image_model: gpt-image-1-mini` (~$1.50/mo) or `cover_image: false` ($0 images) in `config.yaml`. Check current prices at https://openai.com/api/pricing.

---

## One-time setup (~45 min)

### 1. Put this on GitHub
- Create a **public** repository on GitHub. Public is what keeps Actions free and gives the images a public URL. Your API keys stay private as Secrets.
- Upload this folder to it.

### 2. Get an OpenAI API key
**Your ChatGPT Plus subscription doesn't cover this.** The API is billed separately and prepaid.
- Go to https://platform.openai.com → **Settings → Billing** and add $5–10 of credit. Turning off auto-recharge caps your spending.
- Go to **Settings → Organization → General** and complete **Verify organization**. OpenAI requires this before you can use its image models.
- Go to **API keys → Create new secret key**. You'll save it as `OPENAI_API_KEY` in step 4.

### 3. Get your Meta credentials
**Requirements:** your Instagram must be a **Business or Creator** account, and it must be **linked to the Pipeline Reception Facebook Page** (Instagram app → Settings → Account type and tools / Linked accounts).

1. Go to https://developers.facebook.com → **My Apps → Create App**. Choose **Business**, or "Other → Business" if asked.
2. In the app, add the **Instagram** product and **Facebook Login for Business**. You can leave the app in *Development* mode, because you're an admin posting to your own accounts.
3. Open the **Graph API Explorer** (Tools menu):
   - Select your app, then **User Token**.
   - Add these permissions: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`, `instagram_content_publish`, `business_management`.
   - Click **Generate Access Token** and approve.
4. Make the token long-lived: open the **Access Token Debugger** (Tools menu), paste the token, then click **Extend Access Token** at the bottom. Copy the new token.
5. Back in Graph API Explorer, paste the long-lived token and run:
   - `GET me/accounts` → find Pipeline Reception and copy its **`id`** (this is `FB_PAGE_ID`) and its **`access_token`** (this is `META_PAGE_TOKEN`). A Page token made from a long-lived user token **doesn't expire**.
   - `GET {FB_PAGE_ID}?fields=instagram_business_account` → copy the id. This is `IG_USER_ID`.

### 4. Add the secrets to GitHub
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `OPENAI_API_KEY` | from step 2 |
| `META_PAGE_TOKEN` | Page access token from step 3 |
| `FB_PAGE_ID` | Page id from step 3 |
| `IG_USER_ID` | Instagram business account id from step 3 |

Also check that **Settings → Actions → General → Workflow permissions** is set to **Read and write**.

### 5. Test it
- Go to **Actions → Auto-post carousel → Run workflow**, and leave "dry run" checked. This only generates slides. Look in `posts/` to see them.
- Run it again with dry run **unchecked** to do a real post.
- After that it runs on its own at 8am, noon and 6pm New York time.

---

## Customizing (all in `config.yaml` unless noted)

| Want to change… | Where |
|---|---|
| What the business does / "assists, never replaces" positioning | `business` |
| Topics, audience, tone, number of slides | `content` |
| Last-slide CTA text | `cta` |
| Cover art style, image model, image quality | `ai.image_*` |
| Posting times, or 2 a day instead of 3 | `schedule.post_hours` (New York hours; daylight saving time is handled) |
| Post to only IG or only FB | `platforms` |
| Brand colors | `brand.colors` (logo files are in `assets/`) |
| The AI writing prompt itself | `autopost/generate.py` → `PROMPT` |

Preview the slide design locally without any keys:
```bash
pip install -r requirements.txt
python -m autopost.main sample                 # plain branded cover
python -m autopost.main sample some-image.png  # cover with your own image
```

## Good to know
- **GitHub's schedule isn't exact.** Runs can start 5–30 minutes late. That's fine for social posts.
- **If the cover image fails** (out of credit, or the API is down), the post still goes out with the plain branded cover.
- **History:** every published post is logged in `history.json`, and the AI is told to avoid the last 60 topics.
- If one platform fails, the other still posts. The run is marked failed, and GitHub emails you.
- **OpenAI model names change over time.** If a run fails with "model not found", update `ai.openai_model` / `ai.image_model` to a current model.
- **Free text option:** set `ai.provider: gemini` and add a `GEMINI_API_KEY` secret from https://aistudio.google.com/apikey to write posts on Google's free tier. Cover images still use OpenAI.
