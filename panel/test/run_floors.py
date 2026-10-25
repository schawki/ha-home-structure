"""The Rooms page (floors) of the Home Structure panel in headless Chromium against a stand-in for Home Assistant.
Usage: python3 test/run_floors.py [output_dir]   (after `npm run build`)"""
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

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"])
    errors = []


    def new(query="?legacy=1", w=1200, h=900):
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
        pg.goto(base + query)
        pg.wait_for_function("document.querySelector('home-structure-panel')?.shadowRoot?.querySelector('.bar')")
        pg.locator("css=home-structure-panel >> [data-tab=rooms]").click()
        pg.wait_for_selector("css=home-structure-panel >> home-structure-floors >> [data-room]")
        return pg

    def q(pg, sel): return pg.locator(f"css=home-structure-panel >> home-structure-floors >> {sel}")
    def reg(pg): return pg.evaluate("window.__reg")
    def log(pg, kind): return pg.evaluate(f"window.__reg.log.filter(m => m.type === '{kind}')")
    def settle(pg): pg.wait_for_function("document.querySelector('home-structure-panel').shadowRoot.querySelector('home-structure-floors').shadowRoot.querySelector('[data-status]').dataset.status !== 'saving'")
    def rooms(pg, fid): return pg.evaluate(f"[...document.querySelector('home-structure-panel').shadowRoot.querySelector('home-structure-floors').shadowRoot.querySelectorAll('[data-floor=\"{fid}\"] [data-room]')].map(e => e.dataset.room)")

    # ---- layout
    pg = new()
    ok(rooms(pg, "ground") == ["salon"] and rooms(pg, "first") == ["cuisine"] and rooms(pg, "") == ["cave"], "each room sits under its floor")
    ok(q(pg, "[data-room=salon] .picture ha-icon").count() == 1, "a room without picture shows its icon")
    ok(q(pg, "[data-action=page-menu]").count() == 1, "with two floors the page menu is there")

    # ---- room editor: update
    q(pg, "[data-room=salon] [data-action=edit-room]").click()
    ok(q(pg, "[data-room-dialog]").count() == 1 and q(pg, ".gid").inner_text().strip() == "salon", "the pencil opens the editor, the ID is read-only")
    ok(q(pg, ".rname").input_value() == "Salon" and q(pg, ".rfloor").input_value() == "ground", "the editor shows the name and the floor")
    ok(q(pg, "[data-label=l1]").count() == 1 and q(pg, "[data-alias=Living]").count() == 1, "labels and aliases are shown")
    ok(q(pg, "[data-cat='sensor.temperature']").count() == 1 and q(pg, "[data-cat='sensor.humidity']").count() == 1, "temperature and humidity are always offered")
    ok(q(pg, "[data-cat='sensor.temperature'] option").count() == 3, "the temperature box offers Default and the two sensors")
    ok(q(pg, "[data-cat] .sensortitle").count() >= 2 and q(pg, "[data-cat*=angle]").count() == 0, "hidden sensors add no category")
    q(pg, ".rname").fill("Salon 2")
    q(pg, ".rfloor").select_option("first")
    q(pg, "[data-action=alias-open]").click(); q(pg, ".alias").fill("Lounge"); q(pg, ".alias").press("Enter")
    q(pg, "[data-action=label-open]").click(); q(pg, ".newlabelinput").fill("Chauffé"); q(pg, "[data-action=label-create]").click()
    q(pg, "[data-field=labels] [data-label]").nth(1).wait_for()
    q(pg, ".choose[data-key='sensor.temperature']").select_option("sensor.salon_temp2")
    pg.screenshot(path=f"{OUT}/f1-room-editor.png")
    q(pg, "[data-action=dialog-save]").click()
    pg.wait_for_selector("css=home-structure-panel >> home-structure-floors >> [data-room-dialog]", state="detached")
    u = log(pg, "config/area_registry/update")[0]
    ok(u["area_id"] == "salon" and u["name"] == "Salon 2" and u["floor_id"] == "first" and u["aliases"] == ["Living", "Lounge"] and u["labels"] == ["l1", "l2"], "saving updates the Home Assistant area")
    ok(pg.evaluate("window.__s.writes.filter(w => w[0] === 'primary')") == [["primary", "salon", "sensor.temperature", "sensor.salon_temp2"]], "the chosen sensor is saved apart")
    ok(sorted(rooms(pg, "first")) == ["cuisine", "salon"], "the card moves to the new floor")

    # ---- room editor: create, picture, errors
    q(pg, "[data-action=add]").click(); q(pg, "[data-action=create-room]").click()
    ok(q(pg, "[data-action=dialog-save]").is_disabled() and q(pg, "[data-panel]").count() == 0, "a new room needs a name; no sensors panel yet")
    q(pg, ".rname").fill("cuisine"); ok(q(pg, "[data-action=dialog-save]").is_disabled(), "a name already used is refused")
    q(pg, ".rname").fill("Bureau")
    q(pg, ".file").set_input_files(files=[{"name": "a.png", "mimeType": "image/png", "buffer": b"\x89PNG"}])
    q(pg, ".preview").wait_for(state="attached")
    ok(pg.evaluate("window.__uploads") == ["/api/image/upload"] and q(pg, ".preview").get_attribute("src") == "/api/image/serve/img1/512x512", "the picture is uploaded and shown")
    q(pg, "[data-action=dialog-save]").click()
    pg.wait_for_selector("css=home-structure-panel >> home-structure-floors >> [data-room-dialog]", state="detached")
    c = log(pg, "config/area_registry/create")[0]
    ok(c["name"] == "Bureau" and "floor_id" not in c and "icon" not in c and c["picture"] == "/api/image/serve/img1/512x512", "an empty floor and icon are not sent")
    ok(rooms(pg, "") == ["cave", "bureau"], "the new room has no floor")
    pg.close()

    pg = new("?legacy=1&failupload=1&failreg=1")
    q(pg, "[data-room=salon] [data-action=edit-room]").click()
    q(pg, ".file").set_input_files(files=[{"name": "a.png", "mimeType": "image/png", "buffer": b"x"}])
    q(pg, "[data-error]").wait_for()
    ok("500" in q(pg, "[data-error]").inner_text(), "a failed upload is told in the dialog")
    q(pg, "[data-action=dialog-save]").click()
    pg.wait_for_function("document.querySelector('home-structure-panel').shadowRoot.querySelector('home-structure-floors').shadowRoot.querySelector('[data-error]').textContent.includes('refused')")
    ok(q(pg, "[data-room-dialog]").count() == 1, "a refused save keeps the dialog open")
    pg.close()

    # ---- floors
    pg = new()
    q(pg, "[data-floor=ground] [data-action=floor-menu]").click(); q(pg, "[data-action=edit-floor]").click()
    ok(q(pg, ".fname").input_value() == "Ground floor" and q(pg, ".flevel").input_value() == "0" and q(pg, ".gid").inner_text().strip() == "ground", "the floor editor shows name, level and ID")
    q(pg, ".fname").fill("Rez"); q(pg, ".flevel").fill("")
    q(pg, "[data-action=dialog-save]").click()
    pg.wait_for_selector("css=home-structure-panel >> home-structure-floors >> [data-floor-dialog]", state="detached")
    u = log(pg, "config/floor_registry/update")[0]
    ok(u["name"] == "Rez" and u["level"] is None and u["icon"] == "mdi:home", "the floor is updated, an empty level is null")
    q(pg, "[data-action=add]").click(); q(pg, "[data-action=create-floor]").click()
    q(pg, ".fname").fill("Toit"); q(pg, ".flevel").fill("2"); q(pg, "[data-action=dialog-save]").click()
    pg.wait_for_selector("css=home-structure-panel >> home-structure-floors >> [data-floor=toit]")
    ok(log(pg, "config/floor_registry/create")[0]["level"] == 2, "a floor can be created")
    ok(q(pg, "[data-floor-delete],[data-action=delete-floor]").count() == 0, "floors cannot be deleted from here")

    # ---- reorder rooms and floors
    q(pg, "[data-room=cuisine] [data-action=edit-room]").click(); q(pg, ".rfloor").select_option("ground"); q(pg, "[data-action=dialog-save]").click()
    pg.wait_for_selector("css=home-structure-panel >> home-structure-floors >> [data-room-dialog]", state="detached")
    q(pg, "[data-floor=ground] [data-action=floor-menu]").click(); q(pg, "[data-action=reorder-rooms]").click()
    q(pg, "[data-room=cuisine] [data-action=room-handle]").focus(); pg.keyboard.press("ArrowLeft")
    pg.wait_for_function("window.__reg.log.some(m => m.type === 'config/area_registry/reorder')")
    ok(log(pg, "config/area_registry/reorder")[0]["area_ids"] == ["cuisine", "salon", "cave"], "reordering sends every area id")
    ok(sorted(log(pg, "config/area_registry/reorder")[0]["area_ids"]) == sorted(a["area_id"] for a in reg(pg)["areas"]), "all the areas are in the list")
    q(pg, "[data-action=rooms-done]").click()
    q(pg, "[data-action=page-menu]").click(); q(pg, "[data-action=reorder-floors]").click()
    q(pg, "[data-floor=first] [data-action=floor-handle]").focus(); pg.keyboard.press("ArrowUp")
    pg.wait_for_function("window.__reg.log.some(m => m.type === 'config/floor_registry/reorder')")
    ok(log(pg, "config/floor_registry/reorder")[0]["floor_ids"][:2] == ["first", "ground"], "floors can be rearranged")
    pg.close()

    # ---- empty and narrow
    ok(not errors, f"no console errors {errors[:3]}")
    b.close()

sys.exit(1 if ok.failed else 0)
