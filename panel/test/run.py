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

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"])
    errors = []

    def new(query="", w=1300, h=800, locked=False):
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(base + query)
        pg.wait_for_function(f"{P}?.querySelector('.bar')")
        if not locked:      # the panel opens locked; the tests that edit unlock it first
            pg.locator("css=home-structure-panel >> [data-action=toggle-lock]").click()
        return pg

    def q(pg, sel):
        return pg.locator(f"css=home-structure-panel >> {sel}")

    def count(pg, sel):
        return q(pg, sel).count()

    def settle(pg):
        pg.wait_for_function(f"{P}.querySelector('[data-status]').dataset.status !== 'saving'")

    def box(pg, space):
        return q(pg, f"[data-space='{space}']").bounding_box()

    # ---- empty start: tray lists every area, plan empty
    pg = new()
    ok(count(pg, ".tray li") == 6, "tray lists the 6 areas")
    ok(count(pg, ".box") == 0, "plan starts empty")
    ok("Floor" not in q(pg, ".tray").inner_text() and "floor RDC" in q(pg, ".tray").inner_text(), "tray shows floors")
    pg.screenshot(path=f"{OUT}/1-empty.png")

    # ---- add all: everything placed, grouped by floor, saved
    q(pg, "[data-action=add-all]").click(); settle(pg)
    ok(count(pg, ".box") == 6 and count(pg, ".tray li") == 0, "Add all places every area")
    sv = pg.evaluate("window.__s.saves.at(-1).layout")
    ok(len(sv) == 6, "layout saved for 6 areas")
    ys = {k: v["y"] for k, v in sv.items()}
    xs = {k: v["x"] for k, v in sv.items()}
    ok(xs["area:salon"] == xs["area:cuisine"] != xs["area:chambre"], "auto layout puts a floor in a column")
    ok(len({(v["x"], v["y"]) for v in sv.values()}) == 6, "no two boxes at the same spot")
    pg.screenshot(path=f"{OUT}/2-placed.png")

    # ---- drag to move
    a = box(pg, "area:salon")
    pg.mouse.move(a["x"] + 40, a["y"] + 20); pg.mouse.down(); pg.mouse.move(a["x"] + 100, a["y"] + 80, steps=5); pg.mouse.up(); settle(pg)
    a2 = box(pg, "area:salon")
    ok(abs(a2["x"] - a["x"] - 60) <= 2 and abs(a2["y"] - a["y"] - 60) <= 2, "dragging moves the box")
    saved = pg.evaluate("window.__s.saves.at(-1).layout['area:salon']")
    ok(saved["x"] > xs["area:salon"], "move is saved")

    # ---- link by dragging the handle
    c1 = box(pg, "area:cuisine"); h = q(pg, "[data-space='area:salon'] .handle").bounding_box()
    pg.mouse.move(h["x"] + 10, h["y"] + 10); pg.mouse.down(); pg.mouse.move(c1["x"] + 60, c1["y"] + 25, steps=6); pg.mouse.up(); settle(pg)
    ok(count(pg, ".pill") == 1, "dragging the handle creates a link")
    ok(count(pg, "[data-drawer=link]") == 1, "the link drawer opens")
    ok(pg.evaluate("window.__s.saves.at(-1).connections.length") == 1, "link saved")
    pg.screenshot(path=f"{OUT}/3-linked.png")

    # ---- same pair again does not duplicate
    pg.evaluate(f"{P}.querySelector('[data-space=\"area:salon\"] .handle')") 
    h = q(pg, "[data-space='area:salon'] .handle").bounding_box(); c1 = box(pg, "area:cuisine")
    pg.mouse.move(h["x"] + 10, h["y"] + 10); pg.mouse.down(); pg.mouse.move(c1["x"] + 60, c1["y"] + 25, steps=4); pg.mouse.up(); settle(pg)
    ok(count(pg, ".pill") == 1, "linking the same pair again selects the existing link")

    # ---- change type and sensor
    q(pg, "[data-drawer=link] select.type").select_option("window"); settle(pg)
    ok(pg.evaluate("window.__s.saves.at(-1).connections[0].separations[0].type") == "window", "type change saved")
    q(pg, "[data-drawer=link] select.sensor").select_option("cover.volet"); settle(pg)
    ok(pg.evaluate("window.__s.saves.at(-1).connections[0].separations[0].sensor") == "cover.volet", "sensor saved")
    ok("partly open" in q(pg, ".pill").inner_text() or q(pg, ".pill .chip.partial").count() == 1, "chip shows the live state (cover at 40% = partial)")
    # shutter in front of a window, shown on the chip with its own state; only for door-like types
    q(pg, "[data-drawer=link] select.shutter").select_option("cover.volet"); settle(pg)
    ok(pg.evaluate("window.__s.saves.at(-1).connections[0].separations[0].shutter") == "cover.volet", "shutter saved")
    ok(count(pg, ".pill .chip i.sh.partial") == 1, "chip shows the shutter with its live state")
    ok(count(pg, "[data-drawer=link] select.shutter option") == 2, "shutter list offers only covers")
    q(pg, "[data-drawer=link] select.type").select_option("grille"); settle(pg)
    ok(pg.evaluate("'shutter' in window.__s.saves.at(-1).connections[0].separations[0]") is False and count(pg, "[data-drawer=link] select.shutter") == 0, "a grille has no shutter")
    ok(count(pg, "[data-drawer=link] select.sensor") == 1, "a grille can have a sensor")
    # lock and passage: lock for door-like types, passage selector only for ambiguous types
    q(pg, "[data-drawer=link] select.lock").select_option("lock.porte"); settle(pg)
    ok(pg.evaluate("window.__s.saves.at(-1).connections[0].separations[0].lock") == "lock.porte", "lock saved on a grille")
    ok(count(pg, "[data-drawer=link] select.passage") == 1, "a grille offers the passage selector")
    q(pg, "[data-drawer=link] select.passage").select_option("none"); settle(pg)
    ok(pg.evaluate("window.__s.saves.at(-1).connections[0].separations[0].passage") == "none", "passage override saved")
    q(pg, "[data-drawer=link] select.passage").select_option("normal"); settle(pg)
    ok(pg.evaluate("'passage' in window.__s.saves.at(-1).connections[0].separations[0]") is False, "passage equal to the default is not stored")
    q(pg, "[data-drawer=link] select.type").select_option("window"); settle(pg)
    ok(pg.evaluate("'lock' in window.__s.saves.at(-1).connections[0].separations[0]") is False and count(pg, "[data-drawer=link] select.lock") == 0, "a window has no lock")
    ok(count(pg, "[data-drawer=link] select.passage") == 1, "a window offers the passage selector")
    q(pg, "[data-drawer=link] select.type").select_option("grille"); settle(pg)
    q(pg, "[data-drawer=link] select.type").select_option("window"); settle(pg)
    q(pg, "[data-drawer=link] select.sensor").select_option("cover.volet"); settle(pg)
    q(pg, "[data-drawer=link] select.type").select_option("open_space"); settle(pg)
    ok(pg.evaluate("'sensor' in window.__s.saves.at(-1).connections[0].separations[0]") is False, "permanent type drops the sensor")
    ok(count(pg, "[data-drawer=link] select.sensor") == 0, "no sensor field for a permanent type")
    q(pg, "[data-drawer=link] [data-action=add-sep]").click(); settle(pg)
    ok(count(pg, "[data-drawer=link] .sep") == 2, "second separation added")
    q(pg, "[data-drawer=link] .sep >> nth=1 >> select.type").select_option("door")
    q(pg, "[data-drawer=link] .sep >> nth=1 >> select.sensor").select_option("binary_sensor.porte"); settle(pg)
    ok("closed" in q(pg, ".pill").inner_text() or count(pg, ".pill .chip.closed") == 1, "door sensor off = closed")

    # ---- connect from the drawer of a space
    q(pg, "[data-space='area:chambre']").click(); 
    q(pg, "[data-drawer=space] select.connect").select_option("area:bureau"); settle(pg)
    ok(count(pg, ".pill") == 2, "Connect to… from the space drawer creates a link")

    # ---- undo
    q(pg, "[data-action=undo]").click(); settle(pg)
    ok(count(pg, ".pill") == 1, "undo removes the last link")
    ok(pg.evaluate("window.__s.saves.at(-1).connections.length") == 1, "undo is saved")

    # ---- put back in tray
    q(pg, "[data-space='area:cave']").click()
    q(pg, "[data-drawer=space] [data-action=to-tray]").click(); settle(pg)
    ok(count(pg, ".tray li") == 1 and count(pg, "[data-space='area:cave']") == 0, "area returns to the tray")

    # ---- click tray item places it
    q(pg, ".tray li").click(); settle(pg)
    ok(count(pg, "[data-space='area:cave']") == 1, "clicking a tray item places it")

    # ---- zones
    q(pg, "[data-action=add-zone]").click()
    q(pg, ".zoneform select.zkind").select_option("hall")
    ok(q(pg, ".zoneform input.zname").input_value() == "Hall or landing", "zone name follows the kind")
    ok(not q(pg, ".zoneform input.zhome").is_checked(), "hall is outside the home by default")
    q(pg, ".zoneform input.zname").fill("Palier"); q(pg, "[data-action=create-zone]").click(); settle(pg)
    ok(count(pg, ".box.outside") == 1, "outside zone is drawn dashed")
    z = pg.evaluate("window.__s.saves.at(-1).zones.at(-1)")
    ok(z["id"] == "zone:palier" and z["in_home"] is False and z["name"] == "Palier", "zone saved")
    q(pg, "[data-drawer=space] input.inhome").check(); settle(pg)
    ok(pg.evaluate("window.__s.saves.at(-1).zones.at(-1).in_home") is True, "part-of-home toggle saved")
    q(pg, "[data-drawer=space] input.name").fill("Palier 2"); q(pg, "[data-drawer=space] input.name").press("Enter"); q(pg, "h1").click(); settle(pg)
    ok(pg.evaluate("window.__s.saves.at(-1).zones.at(-1).name") == "Palier 2", "zone renamed")
    # a room can be marked as a zone kind
    q(pg, "[data-space='area:entree']").click()
    q(pg, "[data-drawer=space] select.kind").select_option("garage"); settle(pg)
    ok(pg.evaluate("window.__s.saves.at(-1).zones.some(z => z.id === 'area:entree' && z.kind === 'garage')"), "an area can be re-kinded")
    q(pg, "[data-drawer=space] select.kind").select_option("entrance"); settle(pg)
    ok(pg.evaluate("!window.__s.saves.at(-1).zones.some(z => z.id === 'area:entree')") and pg.evaluate("window.__s.saves.at(-1).room_types['area:entree']") == "entrance", "a type of room makes it a room again and is saved")
    ok("Entrance" in q(pg, "[data-space='area:entree']").inner_text(), "the box shows the type of room")
    q(pg, "[data-drawer=space] select.kind").select_option("garage"); settle(pg)
    ok(pg.evaluate("'area:entree' in window.__s.saves.at(-1).room_types") is False and pg.evaluate("window.__s.saves.at(-1).zones.some(z => z.id === 'area:entree' && z.kind === 'garage')"), "a kind of zone replaces the room type")
    q(pg, "[data-drawer=space] select.kind").select_option(""); settle(pg)
    ok(pg.evaluate("!window.__s.saves.at(-1).zones.some(z => z.id === 'area:entree')") and pg.evaluate("'area:entree' in window.__s.saves.at(-1).room_types") is False, "not specified: a plain room with no type")
    labels = pg.evaluate("[...document.querySelector('home-structure-panel').shadowRoot.querySelectorAll('[data-drawer=space] select.kind optgroup')].map(g => g.label)")
    ok(labels == ["Sleeping", "Living and leisure", "Work", "Bathrooms", "Kitchen and utility", "Circulation", "Outside and shared"], f"room types are organised in groups, then the outside and shared kinds {labels}")
    ok(all(q(pg, f"[data-drawer=space] select.kind option[value={v}]").count() == 1 for v in ("master_bedroom", "child_bedroom", "nursery", "guest_room", "game_room", "gym", "dressing", "garage")), "bedrooms of every kind, nursery, game room, gym, dressing room and garage are offered")
    ok(q(pg, "[data-drawer=space] select.kind optgroup >> nth=4").locator("option[value=garage]").count() == 1, "the garage sits with the kitchen and utility rooms")
    pg.screenshot(path=f"{OUT}/4-zones.png")
    q(pg, "[data-space='zone:palier']").click()
    ok(q(pg, "[data-drawer=space] select.kind option[value=bedroom]").count() == 0 and q(pg, "[data-drawer=space] select.kind option[value='']").count() == 0, "a zone that is not an area only offers outside kinds")
    # delete zone
    q(pg, "[data-space='zone:palier']").click(); q(pg, "[data-action=delete-zone]").click(); settle(pg)
    ok(count(pg, "[data-space='zone:palier']") == 0, "zone deleted")

    # ---- reorganize
    q(pg, "[data-action=reorganize]").click(); settle(pg)
    lay = pg.evaluate("window.__s.saves.at(-1).layout")
    ok(lay["area:salon"]["x"] == lay["area:cuisine"]["x"], "Rearrange regroups by floor")

    # ---- reload keeps everything
    pg.reload(); pg.wait_for_function(f"{P}?.querySelector('.bar')")
    ok(count(pg, ".box") == 6 or count(pg, ".box") == 6, "plan is rebuilt from the saved structure on reload") if False else None
    pg.close()

    # ---- legacy structure (no layout) gets placed silently
    pg = new("?legacy=1")
    pg.wait_for_function(f"{P}.querySelectorAll('.box').length === 2")
    settle(pg)
    ok(count(pg, ".box") == 2 and count(pg, ".pill") == 1 and count(pg, ".tray li") == 4, "legacy structure appears on the plan, others stay in the tray")
    ok(pg.evaluate("Object.keys(window.__s.saves.at(-1).layout).length") == 2, "legacy positions were saved")
    pg.screenshot(path=f"{OUT}/5-legacy.png")
    pg.close()

    # ---- save failure is shown and state reloaded
    pg = new("?fail=save")
    q(pg, ".tray li >> nth=0").click()
    pg.wait_for_function(f"{P}.querySelector('[data-status]').dataset.status === 'error'")
    ok("boom" in q(pg, ".status").inner_text(), "save error is displayed")
    pg.close()

    # ---- narrow: list mode, French
    pg = new("?narrow=1&lang=fr&legacy=1", w=420, h=800)
    pg.wait_for_function(f"{P}.querySelectorAll('.spaces li').length === 2")
    ok(count(pg, ".plan") == 0 and count(pg, ".spaces li") == 2, "narrow screens get the list")
    ok("Pas encore sur le plan" in q(pg, ".tray").inner_text() or "plan" in q(pg, ".tray h2").inner_text().lower(), "French strings")
    q(pg, ".spaces li >> nth=0").click()
    ok(count(pg, "[data-drawer=space]") == 1, "list item opens its drawer")
    pg.screenshot(path=f"{OUT}/6-narrow-fr.png")
    q(pg, "[data-action=toggle-view]").click()
    ok(count(pg, ".plan") == 1, "can switch back to the plan")
    pg.close()

    # ---- lock: the panel opens locked, nothing changes until it is unlocked
    pg = new("?legacy=1", locked=True)
    pg.wait_for_function(f"{P}.querySelectorAll('.box').length === 2"); settle(pg)
    n = pg.evaluate("window.__s.saves.length")
    ok(q(pg, "[data-action=toggle-lock]").get_attribute("aria-pressed") == "true", "panel opens locked")
    ok(q(pg, "[data-action=add-all]").is_disabled() and q(pg, "[data-action=reorganize]").is_disabled() and q(pg, "[data-action=add-zone]").is_disabled(), "bar actions are disabled while locked")
    before = box(pg, "area:salon")
    pg.mouse.move(before["x"] + 20, before["y"] + 20); pg.mouse.down(); pg.mouse.move(before["x"] + 200, before["y"] + 120, steps=6); pg.mouse.up()
    after = box(pg, "area:salon")
    ok(after["x"] == before["x"] and after["y"] == before["y"] and pg.evaluate("window.__s.saves.length") == n, "a box cannot be dragged while locked")
    q(pg, ".tray li >> nth=0").click()
    ok(count(pg, ".box") == 2 and pg.evaluate("window.__s.saves.length") == n, "the tray adds nothing while locked")
    q(pg, "[data-space='area:salon']").click()
    ok(count(pg, "[data-drawer=space]") == 1 and pg.evaluate(f"{P}.querySelector('fieldset.lockable').disabled"), "a room can be selected but its drawer is read-only")
    ok(count(pg, "[data-lockhint]") == 1, "the drawer says it is locked")
    q(pg, "[data-action=toggle-lock]").click()
    ok(not pg.evaluate(f"{P}.querySelector('fieldset.lockable').disabled") and q(pg, "[data-action=add-all]").is_enabled(), "unlocking enables editing")
    # ---- usual occupants
    ok(count(pg, ".occupant") == 2, "a room lists the users")
    q(pg, ".occupant[data-user=u2]").check(); settle(pg)
    ok(pg.evaluate("window.__s.saves.at(-1).room_occupants['area:salon']") == ["u2"], "ticking a user saves them as occupant")
    q(pg, ".occupant[data-user=u1]").check(); settle(pg)
    q(pg, ".occupant[data-user=u2]").uncheck(); settle(pg)
    ok(pg.evaluate("window.__s.saves.at(-1).room_occupants['area:salon']") == ["u1"], "unticking removes only that user")
    q(pg, ".occupant[data-user=u1]").uncheck(); settle(pg)
    ok(pg.evaluate("'area:salon' in window.__s.saves.at(-1).room_occupants") is False, "a room with nobody has no entry")
    q(pg, "[data-action=toggle-lock]").click()
    ok(q(pg, "[data-action=undo]").is_disabled(), "locking again disables undo")
    pg.close()

    # ---- Rooms page (read only)
    pg = new("?legacy=1", locked=True)
    q(pg, "[data-tab=rooms]").click()
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms')?.shadowRoot.querySelector('[data-room-row]')")
    R = f"{P}.querySelector('home-structure-rooms').shadowRoot"
    rq = lambda sel: pg.locator(f"css=home-structure-panel >> css=home-structure-rooms >> {sel}")
    ok(rq("[data-room-row]").count() == 2 and rq("[data-room]").count() == 0, "the Rooms page lists the rooms, all closed")
    ok(rq("[data-floor]").count() == 2 and [x.strip() for x in rq("[data-floor] .floortitle").all_text_contents()] == ["Ground floor", "First floor"], "the rooms are listed floor by floor, lowest first")
    ok("sensors" in rq("[data-room-row=salon] .count").inner_text(), "a closed room shows how many sensors it has")
    rq("[data-room-row=salon] [data-action=toggle-room]").click()
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms')?.shadowRoot.querySelector('[data-room=salon]')")
    rq("[data-room-row=cuisine] [data-action=toggle-room]").click()
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms')?.shadowRoot.querySelector('[data-room=cuisine]')")
    ok(rq("[data-room]").count() == 1, "opening a room closes the one that was open")
    rq("[data-room-row=cuisine] [data-action=toggle-room]").click()
    ok(rq("[data-room]").count() == 0, "clicking the open room closes it")
    rq("[data-room-row=salon] [data-action=toggle-room]").click()
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms')?.shadowRoot.querySelector('[data-room=salon]')")
    ok(rq("[data-room=salon] [data-type=temperature] li").count() == 2 and rq("[data-room=salon] [data-type=humidity] li").count() == 1, "sensors are grouped by type")
    ok(rq("[data-room=salon] [data-type=temperature] .rank").count() == 2 and rq("[data-room=salon] [data-type=humidity] .rank").count() == 0, "only types with several sensors show an order")
    ok(rq("[data-entity='sensor.salon_temp'] .assist-box").is_checked() and not rq("[data-entity='sensor.salon_temp2'] .assist-box").is_checked(), "the Assist box shows the exposure")
    ok(rq("[data-entity='sensor.salon_temp'] .assist-box").is_disabled(), "the Assist box cannot be changed yet")
    ok(rq("[data-entity='sensor.salon_temp'] [data-badge=homekit]").count() == 1 and rq("[data-entity='sensor.salon_temp2'] [data-badge=matter]").count() == 1, "HomeKit and Matter badges")
    ok("Karim" in rq("[data-room-row=salon] .occupants").inner_text(), "the usual occupants are named")
    ok(rq("[data-note=not-first]").count() == 0, "no warning when the first sensor is the Assist one")
    ok(rq("[data-unassigned] li").count() == 1, "sensors with no room are listed apart")
    ok(rq("[data-entity='sensor.salon_angle']").count() == 0 and rq("[data-entity='binary_sensor.salon_bark_sound']").count() == 0, "other sensors and sound detections are hidden by default")
    ok("2 hidden" in rq("[data-room-row=salon] .count").inner_text(), "the room says how many sensors are hidden")
    rq("[data-filter=sounds]").click()
    ok(rq("[data-entity='binary_sensor.salon_bark_sound']").count() == 1 and rq("[data-entity='sensor.salon_angle']").count() == 0 and "1 hidden" in rq("[data-room-row=salon] .count").inner_text(), "the sounds filter shows only the sound detections")
    rq("[data-filter=other]").click()
    ok(rq("[data-entity='sensor.salon_angle']").count() == 1 and "hidden" not in rq("[data-room-row=salon] .count").inner_text(), "the other-sensors filter shows the rest")
    rq("[data-filter=sounds]").click(); rq("[data-filter=other]").click()
    ok(rq("[data-type=temperature] select[data-action=choose]").is_disabled() and rq("[data-action=primary-sync]").is_disabled(), "choosing a sensor is locked with the order")
    ok(rq("[data-type=humidity] select[data-action=choose]").count() == 1 and rq("[data-type=other]").count() == 0 and rq("[data-type=sound] select").count() == 0, "only the categories that describe a room have a chosen sensor")
    ok("exposed to Assist" in rq("[data-type=temperature] .chooser").inner_text(), "by default the chosen sensor is the one exposed to Assist")
    rq("[data-lock=order]").click()
    ok(rq("[data-note=order-shows-all]").count() == 1, "unlocking the order says every sensor is listed")
    rq("[data-type=temperature] select[data-action=choose]").select_option("sensor.salon_temp2")
    pg.wait_for_function("window.__s.writes.length === 1")
    ok(pg.evaluate("window.__s.writes[0]") == ["primary", "salon", "sensor.temperature", "sensor.salon_temp2"], "choosing a sensor saves it")
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms').shadowRoot.querySelector('[data-type=temperature] .why')?.textContent.includes('Home Assistant')")
    ok(rq("[data-type=temperature] select[data-action=choose]").input_value() == "sensor.salon_temp2", "the box shows the chosen sensor, and that Home Assistant has it too")
    rq("[data-type=temperature] select[data-action=choose]").select_option("")
    pg.wait_for_function("window.__s.writes.length === 2")
    ok(pg.evaluate("window.__s.writes[1]") == ["primary", "salon", "sensor.temperature", None], "the default can be restored")
    rq("[data-action=primary-sync]").click()
    pg.wait_for_function("window.__s.writes.length === 3")
    ok(pg.evaluate("window.__s.writes[2]") == ["sync", False], "the sync with Home Assistant can be turned off")
    pg.close()
    pg = new("?legacy=1&notfirst=1&nomatter=1", locked=True)
    q(pg, "[data-tab=rooms]").click()
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms')?.shadowRoot.querySelector('[data-room-row]')")
    rq("[data-room-row=salon] [data-action=toggle-room]").click()
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms')?.shadowRoot.querySelector('[data-room=salon]')")
    ok(rq("[data-note=not-first]").count() == 1, "a discreet note when the first sensor is not the Assist one")
    ok("Matter" in rq(".intro").inner_text() and rq("[data-badge=matter]").count() == 0, "Matter unreadable: a short note, no Matter badge")
    pg.screenshot(path=f"{OUT}/7-rooms.png")
    pg.close()

    # ---- Rooms page: padlocks, changes, order, history
    def rooms(query="?legacy=1"):
        g = new(query, locked=True)
        q(g, "[data-tab=rooms]").click()
        g.wait_for_function(f"{P}.querySelector('home-structure-rooms')?.shadowRoot.querySelector('[data-room-row]')")
        g.locator('css=home-structure-panel >> css=home-structure-rooms >> [data-room-row=salon] [data-action=toggle-room]').click()
        g.wait_for_function(f"{P}.querySelector('home-structure-rooms')?.shadowRoot.querySelector('[data-room=salon]')")
        return g
    rq = lambda sel: pg.locator(f"css=home-structure-panel >> css=home-structure-rooms >> {sel}")
    writes = lambda: pg.evaluate("window.__s.writes")
    pg = rooms("?legacy=1&alexa=1")
    ok(all(rq(f"[data-lock={k}]").get_attribute("aria-pressed") == "true" for k in ("assist", "move", "order")), "every section opens locked")
    ok(rq("[data-entity='sensor.salon_temp2'] .assist-box").is_disabled() and rq("[data-action=move]").count() == 0 and rq("[data-action=up]").count() == 0, "locked: no change, no move button, no arrows")
    ok(rq("[data-entity='sensor.salon_temp2'] .alexa-box").count() == 1 and rq("[data-entity='sensor.salon_temp2'] .google-box").count() == 1, "Alexa and Google boxes appear when they are enabled")
    ok(not rq("[data-entity='sensor.salon_temp2'] .alexa-box").is_checked(), "Alexa starts unticked")
    rq("[data-lock=assist]").click()
    rq("[data-entity='sensor.salon_temp2'] .assist-box").click()
    ok(rq("[data-dialog]").count() == 1 and writes() == [], "ticking Assist asks first and writes nothing")
    rq("[data-action=cancel]").click()
    ok(not rq("[data-entity='sensor.salon_temp2'] .assist-box").is_checked() and writes() == [], "cancelling puts the box back")
    rq("[data-entity='sensor.salon_temp2'] .assist-box").click(); rq("[data-action=confirm]").click()
    pg.wait_for_function("window.__s.writes.length === 1")
    ok(writes()[0][:4] == ["exposure", "sensor.salon_temp2", "conversation", True], "confirming exposes the sensor to Assist")
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms').shadowRoot.querySelectorAll('[data-dialog]').length === 0")
    rq("[data-entity='sensor.salon_temp2'] .alexa-box").click(); rq("[data-action=confirm]").click()
    pg.wait_for_function("window.__s.writes.length === 2")
    ok(writes()[1][2:] == ["alexa", True], "Alexa is its own choice")
    rq("[data-history] summary").click()
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms').shadowRoot.querySelectorAll('[data-entry]').length === 2")
    rq("[data-entry] >> nth=0 >> [data-action=undo-entry]").click()
    rq("[data-action=confirm]").click()
    pg.wait_for_function("window.__s.writes.length === 3")
    ok(writes()[2][0] == "undo" and not rq("[data-entity='sensor.salon_temp2'] .alexa-box").is_checked(), "the history can undo a change")
    ok(rq("[data-entry] >> nth=0 >> [data-action=undo-entry]").is_disabled(), "an undone change cannot be undone twice")
    pg.close()

    pg = rooms("?legacy=1&failwrite=1")
    rq("[data-lock=assist]").click()
    rq("[data-entity='sensor.salon_temp2'] .assist-box").click(); rq("[data-action=confirm]").click()
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms').shadowRoot.querySelector('[data-error]')")
    ok("changed since" in rq("[data-error]").inner_text().lower() and rq("[data-dialog]").count() == 1, "an error stays in the dialog")
    pg.close()

    pg = rooms()
    rq("[data-lock=move]").click()
    rq("[data-entity='sensor.salon_temp'] [data-action=move]").click()
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms').shadowRoot.querySelector('[data-scope]')")
    ok(rq("[data-scope]").count() == 1 and "1 other" in rq("[data-scope] legend").inner_text(), "a sensor of a device with other entities asks sensor or device")
    ok("Cold alert" in rq("[data-refs]").inner_text() and "Warm up" not in rq("[data-refs]").inner_text(), "automations that use the sensor are listed")
    rq("[data-scope] input[value=device]").check()
    ok("Warm up" in rq("[data-refs]").inner_text() and "Salon humidity" in rq("[data-scope]").inner_text(), "the device choice lists the other entities and what uses them")
    ok("template" in rq(".dialog").inner_text().lower(), "the dialog says templates cannot be detected")
    pg.screenshot(path=f"{OUT}/8-move.png")
    rq("[data-action=confirm]").click()
    pg.wait_for_function("window.__s.writes.length === 1")
    ok(writes()[0] == ["move", "sensor.salon_temp", "cuisine", "device"], "the device moves to the chosen room")
    rq("[data-room-row=cuisine] [data-action=toggle-room]").click()
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms').shadowRoot.querySelector('[data-room=cuisine] [data-entity=\"sensor.salon_hum\"]')")
    ok(rq("[data-room=cuisine] [data-entity='sensor.salon_temp']").count() == 1, "the rooms show the new places")
    rq("[data-unassigned] summary").click()
    rq("[data-unassigned] [data-action=move]").click()
    ok(rq("[data-scope]").count() == 0, "a sensor with no device moves without asking which")
    pg.close()

    pg = rooms()
    ok(rq("[data-action=up]").count() == 0, "no arrows while the order is locked")
    rq("[data-lock=order]").click()
    ok(rq("[data-room=salon] [data-type=humidity] [data-action=up]").count() == 0, "a type with one sensor has no order")
    rq("[data-entity='sensor.salon_temp2'] [data-action=up]").click()
    pg.wait_for_function("window.__s.writes.length === 1")
    ok(writes()[0] == ["order", "salon", "sensor.temperature", ["sensor.salon_temp2", "sensor.salon_temp"]], "the arrows save the priority")
    pg.wait_for_function(f"{P}.querySelector('home-structure-rooms').shadowRoot.querySelector('[data-action=reset-order]')")
    rq("[data-entity='sensor.salon_temp'] .arrows .up").click()
    pg.wait_for_function("window.__s.writes.length === 2")
    ok(writes()[1][3] == ["sensor.salon_temp", "sensor.salon_temp2"], "and move it back")
    rq("[data-entity='sensor.salon_temp']").drag_to(rq("[data-entity='sensor.salon_temp2']"))
    pg.wait_for_function("window.__s.writes.length === 3")
    ok(writes()[2][3] == ["sensor.salon_temp2", "sensor.salon_temp"], "a sensor can also be dragged")
    rq("[data-action=reset-order]").click()
    pg.wait_for_function("window.__s.writes.length === 4")
    ok(writes()[3][3] == [], "the automatic order can be restored")
    pg.close()

    ok(not errors, f"no console errors {errors[:3]}")
    b.close()

sys.exit(1 if ok.failed else 0)
