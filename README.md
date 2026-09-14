# Verso

**Verso matches complementary people. It does not match like-minded ones.**

> Most social products thicken the filter bubble: they pair you with people who already share your domain, taste, and worldview. Verso does the opposite. It uses a question to pair two people who can teach each other — different fields, different ways of thinking — so both leave knowing something they did not.

[Quick start](#quick-start) · [中文文档](README_zh.md)

The name is **Verso**; the other side of a page. Two sides look opposed. Closed, they are one sheet.

---

## The match

A match succeeds only when both sides complete each other:

| This side | Gets |
| --- | --- |
| What you are good at | Taught to someone who is not |
| What you want to learn this time | Learned from the other person |

![Verso complementary match](docs/assets/verso-complementary-match.en.svg)

Same-topic, same-article, and same-question pairing are out of scope. Authorized Zhihu articles, follows, and favorites only build a strengths portrait. They are not a chat map, and they are not the match condition.

---

## What Verso provides

| Capability | What it does |
| --- | --- |
| Auth | Zhihu OAuth; store the account and authorized public work |
| Portrait | Turn that work into a strengths portrait |
| Match | Pair two people whose strengths cover each other's one-time question |
| Exchange | Async 1:1 messages under that pair |
| Quality | Score an answer only after someone marks it unsatisfactory |
| Reputation | Persist score and matching eligibility |

Core path: **auth → portrait → complementary match → async exchange → quality → reputation**.

---

## Specs

Product and module boundaries live in GitHub issues. Agents and developers should read those, not a second copy in `/docs`.

- Product proposal: [#30](https://github.com/xiaocheny214/verso/issues/30)
- Module split: [#31](https://github.com/xiaocheny214/verso/issues/31)
- How to contribute: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

Local API notes: [backend/README.md](backend/README.md).

The frontend container writes static files to `/var/www/verso-frontend` and exits. Host Nginx uses [`deploy/nginx/verso.host.conf`](deploy/nginx/verso.host.conf): `root` points at that directory, API traffic proxies to `127.0.0.1:8000`. Data lives in `./data/postgres` and `./data/redis`.

---

## Repository layout

```text
verso/
├── frontend/           # Next.js; image writes static files to /var/www/verso-frontend
├── backend/            # uv workspace: common → framework → app
├── deploy/             # host Nginx example
└── docker-compose.yml
```

---

## License

Proprietary commercial. See [LICENSE](LICENSE).
