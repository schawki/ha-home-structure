"""Loads the built Home Structure panel in headless Chromium against a stand-in for Home Assistant, checks behaviour, writes screenshots.
Usage: python3 test/run.py [output_dir]   (after `npm run build`)"""
import http.server, os, sys, threading
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "..", "..", "custom_components", "home_structure", "frontend", "home-structure-panel.js")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        files = {"/": (os.path.join(HERE, "harness.html"), "text/html"), "/panel.js": (BUILD, "text/javascript")}
        if path not in files:
            self.send_response(404 if path != "/favicon.ico" else 204); self.end_headers(); return
        name, ctype = files[path]
        self.send_response(200); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(open(name, "rb").read())

    def log_message(self, *a): pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}/"


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        ok.failed = True
ok.failed = False

P = "document.querySelector('home-structure-panel').shadowRoot"


SHOTS = os.path.join(HERE, "..", "..", "docs", "images")
os.makedirs(SHOTS, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1300, "height": 640})
    pg.goto(base)
    pg.wait_for_function(f"{P}?.querySelector('.bar')")
    def q(sel): return pg.locator(f"css=home-structure-panel >> {sel}")
    def settle(): pg.wait_for_function(f"{P}.querySelector('[data-status]').dataset.status !== 'saving'")
    q("[data-action=add-all]").click(); settle()
    def link(a, c):
        bx = q(f"[data-space='{c}']").bounding_box(); h = q(f"[data-space='{a}'] .handle").bounding_box()
        pg.mouse.move(h["x"] + 10, h["y"] + 10); pg.mouse.down(); pg.mouse.move(bx["x"] + 60, bx["y"] + 25, steps=6); pg.mouse.up(); settle()
    link("area:chambre", "area:bureau")
    link("area:entree", "area:salon")
    link("area:cuisine", "area:entree")
    pg.screenshot(path=os.path.join(SHOTS, "plan.png"))
    b.close()
