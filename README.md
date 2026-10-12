# Climate Hazard Trend Analyzer

A web app that measures how heatwaves have changed for a city, a state or region, or a box you draw on a map. The default hazard is heatwave. Temperatures come from the public Open-Meteo archive (ERA5 reanalysis). No API key is required.

The backend is Python (FastAPI). The frontend is React (Vite, TypeScript, Tailwind). Weather series and finished analyses are stored as JSON documents.

## Setup

Requirements: Python 3.12, Node.js 22 (or 20+). MongoDB is optional.

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

Run the API and the UI in two terminals:

```bash
make api    # http://127.0.0.1:8765
make web    # http://127.0.0.1:43123
```

Or without Make:

```bash
cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8765 --reload
cd frontend && npm run dev
```

Open [http://127.0.0.1:43123](http://127.0.0.1:43123). The page loads Delhi, 1990–2025, against a 1961–1990 baseline. The first request downloads the temperature archive and writes it to the document store. Repeat requests for the same place and years are reads.

Tests:

```bash
make test
```

Interactive API docs: [http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs).

### Environment

Copy `backend/.env.example` to `backend/.env` only if you need to change defaults.

| Variable | Default | Role |
| --- | --- | --- |
| `MONGO_URI` | empty | MongoDB connection string. Empty uses TinyDB. |
| `MONGO_DB` | `climate_hazard` | Database name |
| `STORE_PREFERENCE` | `auto` | `auto`, `mongo`, or `tinydb` |
| `CORS_ORIGINS` | local UI origins | Comma-separated browser origins |
| `TRUST_PROXY` | `false` | Trust `X-Forwarded-For` for rate limits. Set `true` on Render. |
| `VITE_API_BASE` | empty | Frontend build-time API origin. Empty means same-origin `/api`. |

## Architecture

```text
React UI  --HTTP-->  FastAPI
                         |
                         +--> document store (MongoDB or TinyDB)
                         |      weather days, analyses, geocodes
                         |
                         +--> Open-Meteo archive (ERA5 daily Tmax)
                         +--> Open-Meteo geocoder
```

- `frontend/` — region search, Leaflet map, Recharts time series, CSV and PDF download.
- `backend/app/api/routes.py` — HTTP API, input checks, rate limits.
- `backend/app/services/heatwave.py` — percentile threshold and event detection.
- `backend/app/services/trends.py` — rolling means, linear regression, Mann–Kendall, Sen's slope.
- `backend/app/services/insights.py` — the sentence on the page. It does not call a trend significant unless the test says so.
- `backend/app/services/analysis.py` — fetch, cache, score, store.
- `backend/app/db/store.py` — one document interface with a MongoDB implementation and a TinyDB implementation.

### API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Process and store type |
| `GET` | `/api/regions` | Featured cities and states |
| `GET` | `/api/geocode?q=` | Place search, cached |
| `POST` | `/api/analyze` | Heatwave summary, yearly series, events, trends |
| `POST` | `/api/export/csv` | CSV for the analysis already on screen |
| `POST` | `/api/export/pdf` | PDF report of that same analysis |

`POST /api/analyze` is limited to 10 requests per minute per IP. Geocoding is 30 per minute. Exports are 20 per minute. Completed historical years are cached indefinitely. The current year is not served from the analysis cache, because the archive can still add days.

## Data source

[Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (`/v1/archive`), variable `temperature_2m_max`, Celsius, timezone UTC. For the years this app requests, that archive is [ERA5](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels) reanalysis at 2 metres. It is a gridded model product, not a single airport station, and the coordinate you pick is snapped to 0.01° (about 1 km) before it is cached.

Place search uses the Open-Meteo geocoder. Featured states are a local catalog of approximate boxes, not legal boundaries.

A city is one point. A state or a custom box is the unweighted mean of up to four interior points. A day is missing if fewer than half of those points have a usable temperature. Boxes larger than 15° on a side are rejected so a request cannot fan out across a continent. The client only calls the Open-Meteo hosts configured in settings.

Values below −80°C or above 55°C are rejected as implausible and break a heatwave run. Gaps are not filled. A missing or rejected day ends the current spell. Recent nulls (the last 14 days) are refetched if the cached document is older than 12 hours, because ERA5 can lag. Older nulls stay cached.

## Heatwave definition

A heatwave is a run of at least **3 consecutive calendar days** (2–10 can be chosen in the UI) whose daily maximum temperature is **strictly above** the **95th percentile** of daily maximum temperature in the baseline.

The default baseline is **1961–1990**. The percentile uses every valid day in those years, not a separate threshold for each calendar day. That makes it a local hot-season extreme: winter warm spells are not labeled heatwaves. The threshold is computed once and then applied to the analysis window. It is not refit on the years being scored.

That choice matters. If the percentile is taken from the same years you are trying to trend, later hot years pull the bar upward and the early part of the record can look like it had no heatwaves. A fixed baseline lets a warmer climate show up as more days above a historical extreme. The tests include a synthetic warming climate that checks this.

Other counting rules:

- An event is attributed to the year it starts.
- Heatwave days are counted in the year they fall. A spell that crosses 1 January can add days to a year that shows no new event.
- Years with less than 80% of days present are excluded from totals and from the trend tests. A missing summer is not stored as a cool year.
- The headline percent change compares mean annual heatwave days in the first and last 10 complete years. Shorter series (still at least 10 years) are split in half. A change under 1% is described as “about the same.”
- If the early window has no heatwave days and the late window does, the headline says that directly instead of printing an infinite percent.
- The 5-year line on the charts is a centered rolling mean. Edges and gaps are left blank.
- Linear regression is ordinary least squares on the complete years.
- The Mann–Kendall test is two-sided, with a continuity correction and a correction for ties. Sen's slope is the median of slopes between every pair of years, divided by the actual year gap. Significance means p < 0.05. Below 20 complete years the normal approximation is rough, and the detail text says so.
- A large percent change with a high p-value is still shown, and it is labeled not statistically significant.

Drought and heavy rainfall appear in the hazard control so heatwave is visibly the selected default. They are disabled. The API rejects any hazard other than `heatwave`.

## Assumptions

- ERA5 daily maxima are an acceptable stand-in for “the region’s” temperature at the sampled points. They are not bias-corrected to a city thermometer, and a coastal point can sit over water in the reanalysis grid.
- An all-year 95th percentile is the definition used here because the task specifies a percentile for the region. It is not the calendar-day index TX95p, and it is not the India Meteorological Department’s absolute thresholds (about 40°C on the plains, plus a departure from normal).
- Four sample points do not describe a large state. Rajasthan and California are illustrative means, not area-weighted fields.
- Overlap between the baseline and the analysis window is allowed. Shared years help set the threshold and are also scored against it. The overlap note is shown in the UI when that happens.
- The archive begins in 1940. The UI default end year is the last complete calendar year.
- Historical years are treated as stable once cached. A later ERA5 revision will not be picked up unless the document store is cleared (`backend/data/documents.json`, or the MongoDB `weather` and `analyses` collections).

## What I would do with more time

- A calendar-day percentile (TX95p) next to the all-year percentile, so the sensitivity of the definition is visible.
- A land mask and more than four sample points, or a single Open-Meteo grid request if one is available for the box.
- Block bootstrap confidence intervals on the slope, which would be more honest than the Mann–Kendall normal approximation on a 15-year series.
- Drought (for example a rainfall percentile or SPEI) and heavy-rain days, using the same cache and chart shell.
- A background job for the first fetch, with progress, instead of a request that can run for half a minute.
- A shared rate-limit store (Redis) if more than one API instance is running.

## Bonus features

- **Map.** Leaflet and CARTO light tiles. Click to drop a point, or click two corners to draw a box. Featured states draw their sampling box. After a run, teal dots mark the coordinates that were actually averaged.
- **CSV and PDF.** Both are generated from the analysis already on screen, so export does not re-download the archive. CSV cells that start with `=`, `+`, `-`, or `@` are prefixed so a spreadsheet does not treat a region name as a formula. The PDF uses DejaVu when the font is installed (it is, in the Docker image) and falls back to Helvetica otherwise.
- **Trends.** Each series reports ordinary least squares (slope per decade, p-value, R²) and a Mann–Kendall test with Sen's slope. The charts draw the regression line and a 5-year rolling mean.

## Document store

Both stores keep the same three collections: `weather` (daily maxima keyed by rounded coordinate), `analyses` (the JSON returned to the UI), and `geocode`.

- **TinyDB** is the default. It is a file-backed document database at `backend/data/documents.json`. Nothing else has to be installed, which is also how the app runs on a free host that does not include MongoDB. The file is ephemeral on Render’s free tier, so the cache is lost on restart and the next request fetches again.
- **MongoDB** is used when `MONGO_URI` is set. `docker compose up` starts MongoDB 7, the API, and the UI, and points the API at Mongo. For Render, a free MongoDB Atlas cluster is the durable option: create a database user, allow network access, and set `MONGO_URI`. Prefer `STORE_PREFERENCE=mongo` in that case so a bad connection string fails loudly instead of silently falling back to a disk that gets wiped.

## Security and limits

- Latitudes, longitudes, years, percentile (90–99), duration, and box size are validated before any archive call.
- Region ids are restricted to a safe character set. Unknown catalog ids are rejected. Names are stripped of control characters.
- The archive client does not follow redirects and only requests the configured Open-Meteo URLs.
- Rate limits are per IP. Behind Render, set `TRUST_PROXY=true` so the limit uses the forwarded client address. Leave it false anywhere else, so a caller cannot spoof the header.
- Responses set `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`.

## Deployment

### Docker Compose (API, MongoDB, UI)

```bash
docker compose up --build
```

UI: [http://localhost:43123](http://localhost:43123). API: [http://localhost:8765](http://localhost:8765). Nginx in the web container proxies `/api` to the API, so the browser stays on one origin.

### Render (API) and Vercel or Netlify (UI)

1. Push this repository.
2. On Render, create a Blueprint from `render.yaml`, or a Docker web service with Dockerfile `backend/Dockerfile` and context `backend`. Health check: `/api/health`.
3. Set `CORS_ORIGINS` to the frontend origin, for example `https://your-app.vercel.app`. Set `TRUST_PROXY=true`.
4. Optional: set `MONGO_URI` to a MongoDB Atlas connection string and `STORE_PREFERENCE=mongo`.
5. On Vercel, import the repo with root directory `frontend`. Set `VITE_API_BASE` to the Render URL, including `https` and with no trailing slash. `frontend/vercel.json` is already a Vite single-page config.
6. On Netlify, the same root and the same `VITE_API_BASE` work with `frontend/netlify.toml`.

Render’s free instance sleeps. The first analysis after a cold start pays for both the wake-up and the archive download. After that, cached years return quickly until the disk is reset.

There is no hosted URL in this repository yet. Deploying needs an account on Render and Vercel or Netlify; the config files are the deploy path.

## Tests

`backend/tests` covers the heatwave rules (3-day minimum, strict inequality, gaps, duplicates, implausible values, year boundaries, regional means), the reason the baseline is held fixed, rolling means, regression, Mann–Kendall including ties and Sen's slope across year gaps, insight wording, catalog boxes, weather and analysis caching, validation, geocoder caching, CSV formula injection, and a PDF that starts with `%PDF`.

The suite does not call Open-Meteo. A fake temperature series stands in for the archive.

## AI tools

This project was built with the help of AI coding assistants. The assistant wrote the application, the tests, the deployment files, and this README from the case-study requirements. The heatwave rule, the decision to keep the baseline threshold fixed, and the wording that refuses to call a noisy change “significant” are implemented in code and locked in by tests, not left as a hidden library call. Open-Meteo was queried while checking that a real archive response could be cached and plotted. A reviewer should still walk the detection code and change it live; that is what the tests are there to support.

## Project layout

```text
backend/app/api/          routes
backend/app/services/     heatwave logic, trends, archive client, exports
backend/app/db/           MongoDB and TinyDB
backend/app/data/         featured cities and regions
backend/tests/            pytest
frontend/src/             React UI
docker-compose.yml        API + MongoDB + UI
render.yaml               Render blueprint for the API
frontend/vercel.json      Vercel
frontend/netlify.toml     Netlify
```
