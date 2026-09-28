"""
Official DOGFOOD 2026 Acceptance Checker Runner.
Executes the 7 standard HTTP verification requests against the running portal
using credentials/headers from .dogfood.toml, evaluates claimed tiers,
and writes acceptance-report.txt.
"""

import sys
import os
import urllib.request
import urllib.error

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


def parse_toml(filepath):
    if tomllib is not None:
        with open(filepath, "rb") as f:
            return tomllib.load(f)
    # Simple fallback parser for .dogfood.toml
    config = {
        "base_url": "http://localhost:8000",
        "metadata": {"claimed_tiers": ["T1", "T2"], "pitch": ""},
        "auth": {"headers": {}},
        "routes": {}
    }
    current_section = None
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                continue
            if "=" in line:
                key, val = [x.strip() for x in line.split("=", 1)]
                val = val.strip('"\'')
                if current_section == "metadata" and key == "claimed_tiers":
                    tiers = [x.strip().strip('"\'') for x in val.strip("[]").split(",") if x.strip()]
                    config["metadata"]["claimed_tiers"] = tiers
                elif current_section == "metadata":
                    config["metadata"][key] = val
                elif current_section == "auth.headers":
                    config["auth"]["headers"][key] = val
                elif current_section == "routes":
                    config["routes"][key] = val
                elif current_section is None and key == "base_url":
                    config["base_url"] = val
    return config


def make_request(url, method="GET", header_str=None, data=None):
    headers = {}
    if header_str:
        if ":" in header_str:
            h_key, h_val = header_str.split(":", 1)
            headers[h_key.strip()] = h_val.strip()
    req = urllib.request.Request(url, method=method, headers=headers)
    if method == "POST":
        req.data = data or b""
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return 0, str(e)


def main():
    config_file = sys.argv[1] if len(sys.argv) > 1 else ".dogfood.toml"
    if not os.path.exists(config_file):
        print(f"Error: configuration file '{config_file}' not found.")
        sys.exit(1)

    cfg = parse_toml(config_file)
    base_url = cfg.get("base_url", "http://localhost:8000").rstrip("/")
    headers = cfg.get("auth", {}).get("headers", {})
    routes = cfg.get("routes", {})
    claimed_tiers = cfg.get("metadata", {}).get("claimed_tiers", ["T1", "T2"])

    report_lines = []
    def log(msg=""):
        print(msg)
        report_lines.append(msg)

    log("=" * 70)
    log("       OFFICIAL DOGFOOD 2026 ACCEPTANCE CHECKER REPORT")
    log("=" * 70)
    log(f"Target Portal Base URL : {base_url}")
    log(f"Claimed Tiers          : {' '.join(claimed_tiers)}")
    log("-" * 70)

    checks = []

    # 1. GET /projects (public, 200, body contains a fixture title)
    route_projects = routes.get("projects", "/projects")
    st, body = make_request(f"{base_url}{route_projects}", method="GET")
    has_title = any(t in body for t in ["AutoDev Copilot", "HyperChain DB", "NeuralMesh", "QuantumQuery"])
    ok1 = (st == 200 and has_title)
    checks.append(("T1", "GET /projects (public, 200, contains fixture project)", ok1, f"status={st}, fixture_title_found={has_title}"))

    # 2. POST /projects/new (as participant -> 4xx, fixture event closed)
    route_new = routes.get("projects_new", "/projects/new")
    h_part = headers.get("participant", "")
    st, body = make_request(f"{base_url}{route_new}", method="POST", header_str=h_part)
    ok2 = (400 <= st < 500)
    checks.append(("T1", "POST /projects/new (as participant -> 4xx closed event)", ok2, f"status={st}"))

    # 3. GET /api/judge/scores (as judge_a -> 200)
    route_scores = routes.get("judge_scores", "/api/judge/scores")
    h_ja = headers.get("judge_a", "")
    st, body = make_request(f"{base_url}{route_scores}", method="GET", header_str=h_ja)
    ok3 = (st == 200)
    checks.append(("T2", "GET /api/judge/scores (as judge_a -> 200)", ok3, f"status={st}"))

    # 4. GET /api/judge/scores (as participant -> 401/403)
    st, body = make_request(f"{base_url}{route_scores}", method="GET", header_str=h_part)
    ok4 = (st in (401, 403))
    checks.append(("T2", "GET /api/judge/scores (as participant -> 401/403)", ok4, f"status={st}"))

    # 5. GET /api/judge/scores?judge=judge_a (as judge_b -> 401/403)
    h_jb = headers.get("judge_b", "")
    st, body = make_request(f"{base_url}{route_scores}?judge=judge_a", method="GET", header_str=h_jb)
    ok5 = (st in (401, 403))
    checks.append(("T2", "GET /api/judge/scores?judge=judge_a (as judge_b -> 401/403)", ok5, f"status={st}"))

    # 6. GET /api/export.csv (as organizer -> 200 with CSV body)
    route_export = routes.get("export_csv", "/api/export.csv")
    h_org = headers.get("organizer", "")
    st, body = make_request(f"{base_url}{route_export}", method="GET", header_str=h_org)
    is_csv = (st == 200 and ("event_slug" in body or "," in body))
    ok6 = is_csv
    checks.append(("T2", "GET /api/export.csv (as organizer -> 200 CSV body)", ok6, f"status={st}, csv_body={is_csv}"))

    # 7. GET /api/export.csv (as participant -> 401/403)
    st, body = make_request(f"{base_url}{route_export}", method="GET", header_str=h_part)
    ok7 = (st in (401, 403))
    checks.append(("T2", "GET /api/export.csv (as participant -> 401/403)", ok7, f"status={st}"))

    verified_tiers = []
    t1_checks = [c for c in checks if c[0] == "T1"]
    t2_checks = [c for c in checks if c[0] == "T2"]

    for tier, name, passed, info in checks:
        status_label = "[PASS]" if passed else "[FAIL]"
        log(f"{status_label} {name} :: {info}")

    if all(c[2] for c in t1_checks):
        verified_tiers.append("T1")
    if all(c[2] for c in t2_checks):
        verified_tiers.append("T2")

    log("-" * 70)
    claimed_str = " ".join(claimed_tiers)
    verified_str = " ".join(verified_tiers)
    final_line = f"SUMMARY: claimed {claimed_str}, verified {verified_str}"
    log(final_line)
    log("=" * 70)

    with open("acceptance-report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")


if __name__ == "__main__":
    main()
