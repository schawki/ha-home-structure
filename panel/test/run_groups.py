"""The Groups tab of the Home Structure panel in headless Chromium against a stand-in for Home Assistant.
Usage: python3 test/run_groups.py [output_dir]   (after `npm run build`)"""
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

    def new(query="?groups=1", w=1200, h=900):
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(base + query)
        pg.wait_for_function("document.querySelector('home-structure-panel')?.shadowRoot?.querySelector('.bar')")
        pg.locator("css=home-structure-panel >> [data-tab=groups]").click()
        pg.wait_for_selector("css=home-structure-panel >> home-structure-groups >> .head")
        return pg

    def q(pg, sel): return pg.locator(f"css=home-structure-panel >> home-structure-groups >> {sel}")
    def n(pg, sel): return q(pg, sel).count()
    def settle(pg): pg.wait_for_function("document.querySelector('home-structure-panel').shadowRoot.querySelector('home-structure-groups').shadowRoot.querySelector('[data-status]').dataset.status !== 'saving'")
    def last(pg): return pg.evaluate("window.__s.groupSaves.at(-1)")
    def rooms(pg, gid): return pg.evaluate(f"[...document.querySelector('home-structure-panel').shadowRoot.querySelector('home-structure-groups').shadowRoot.querySelectorAll('[data-group=\"{gid}\"] [data-room]')].map(e => e.dataset.room)")
    def order(pg): return pg.evaluate("[...document.querySelector('home-structure-panel').shadowRoot.querySelector('home-structure-groups').shadowRoot.querySelectorAll('[data-group]:not(.ungrouped)')].map(e => e.dataset.group)")

    # ---- empty: hint, no group, + Add
    pg = new("")
    ok(n(pg, "[data-empty]") == 1 and n(pg, ".group") == 0, "no group yet: the hint is shown")
    ok(n(pg, "[data-action=add-group]") == 1 and n(pg, "[data-action=page-menu]") == 0, "the + Add button is there, no page menu with fewer than two groups")
    pg.screenshot(path=f"{OUT}/g1-empty.png")

    # ---- create a group with rooms, aliases, sensors
    q(pg, "[data-action=add-group]").click()
    ok(n(pg, ".dialog") == 1 and q(pg, "input.gid").is_disabled(), "the dialog opens with a disabled ID")
    ok(q(pg, "[data-action=dialog-save]").is_disabled(), "Save waits for a name")
    q(pg, "input.gname").fill("Night part")
    ok(q(pg, "input.gid").input_value() == "night_part", "the ID follows the name")
    q(pg, "input.glevel").fill("1"); q(pg, "input.gicon").fill("mdi:bed")
    q(pg, "select.addroom").select_option("chambre"); q(pg, "select.addroom").select_option("bureau")
    ok(n(pg, "[data-field=rooms] .chip") == 2 and "Chambre" in q(pg, "[data-field=rooms]").inner_text(), "rooms are added as chips")
    ok(n(pg, "select.addroom option[value=chambre]") == 0, "a room already chosen is no longer offered")
    q(pg, "input.alias").fill("Nuit"); q(pg, "input.alias").press("Enter"); q(pg, "input.alias").fill("Dodo")
    ok(n(pg, "[data-field=aliases] .chip") == 1, "Enter adds an alias")
    t = "[data-kind=temperature]"
    q(pg, f"{t} select.mode").select_option("single")
    ok(n(pg, f"{t} select.sensor option") == 3, "one sensor: the two rooms' temperature sensors are offered")
    ok(q(pg, f"{t} select.sensor").input_value() == "sensor.chambre_temp", "the first sensor is preselected")
    q(pg, f"{t} select.mode").select_option("all")
    ok(n(pg, f"{t} [data-source]") == 2 and "19" in q(pg, f"{t} [data-source]").first.inner_text(), "average of all: the sources are listed with their values")
    q(pg, f"{t} select.mode").select_option("selection")
    ok(n(pg, f"{t} input[type=checkbox]") == 2 and n(pg, f"{t} input[type=checkbox]:checked") == 2, "a selection starts with every sensor ticked")
    q(pg, f"{t} input[data-sensor='sensor.bureau_temp']").uncheck()
    q(pg, "[data-kind=humidity] select.mode").select_option("selection")
    q(pg, "[data-kind=humidity] input[data-sensor='sensor.chambre_hum']").uncheck()
    q(pg, "[data-kind=humidity] input[data-sensor='sensor.bureau_hum']").uncheck()
    ok(q(pg, "[data-action=dialog-save]").is_disabled(), "an empty selection cannot be saved")
    pg.screenshot(path=f"{OUT}/g2-dialog.png")
    q(pg, "[data-kind=humidity] select.mode").select_option("all")
    q(pg, "[data-action=dialog-save]").click(); settle(pg)
    g = last(pg)[0]
    ok(g["name"] == "Night part" and g["level"] == 1 and g["icon"] == "mdi:bed" and g["areas"] == ["chambre", "bureau"] and g["aliases"] == ["Nuit", "Dodo"], f"the group is saved {g['aliases']}")
    ok(g["temperature"] == {"mode": "selection", "entities": ["sensor.chambre_temp"]} and g["humidity"] == {"mode": "all", "entities": []}, "sensor settings saved")
    ok(n(pg, ".dialog") == 0 and n(pg, "[data-group=night_part] [data-room]") == 2, "the dialog closes and the group appears with its rooms")
    ok(n(pg, "[data-group='']") == 1 and n(pg, "[data-group=''] [data-room]") == 4, "the other rooms are listed as not in any group")
    pg.close()

    # ---- existing groups
    pg = new()
    ok(order(pg) == ["nuit", "jour", "vide"] and rooms(pg, "jour") == ["salon", "cuisine", "chambre"], "groups and rooms keep their order")
    ok(n(pg, "[data-group=vide] [data-room]") == 0 and n(pg, "[data-group=vide] .muted") >= 1, "an empty group says so")
    ok("2 rooms" in q(pg, "[data-group=nuit] header").inner_text() and "3 rooms" in q(pg, "[data-group=jour] header").inner_text(), "room counts")
    ok(rooms(pg, "") == ["entree", "cave"], "rooms of no group")
    pg.screenshot(path=f"{OUT}/g3-groups.png")

    # ---- room menu: a room in two groups
    q(pg, "[data-group=nuit] [data-room=chambre] [data-action=room-menu]").click()
    labels = q(pg, ".menu .item").all_inner_texts()
    ok(labels == ["Add to another group…", "Remove from this group", "Remove from all groups"] or "Remove from all groups" in labels, f"menu of a room in two groups {labels}")
    ok("Move to another group…" in labels, "Move is offered when another group is free")
    q(pg, ".menu [data-action=remove-all]").click(); settle(pg)
    ok(rooms(pg, "nuit") == ["bureau"] and rooms(pg, "jour") == ["salon", "cuisine"], "Remove from all groups takes the room out of both")
    # move
    q(pg, "[data-group=jour] [data-room=salon] [data-action=room-menu]").click()
    q(pg, ".menu [data-action=move-room]").click()
    ok(n(pg, ".dialog.small") == 1 and n(pg, "select.target option") == 2, "Move opens a chooser of the other groups")
    q(pg, "select.target").select_option("nuit"); q(pg, "[data-action=mover-ok]").click(); settle(pg)
    ok(rooms(pg, "nuit") == ["bureau", "salon"] and rooms(pg, "jour") == ["cuisine"], "Move transfers the room")
    # add to another group
    q(pg, "[data-group=jour] [data-room=cuisine] [data-action=room-menu]").click()
    q(pg, ".menu [data-action=add-room]").click(); q(pg, "[data-action=mover-ok]").click(); settle(pg)
    ok("cuisine" in rooms(pg, "jour") and ("cuisine" in rooms(pg, "nuit") or "cuisine" in rooms(pg, "vide")), "Add keeps the room in both groups")
    # remove from this group only
    q(pg, "[data-group=nuit] [data-room=bureau] [data-action=room-menu]").click(); q(pg, ".menu [data-action=remove-room]").click(); settle(pg)
    ok("bureau" not in rooms(pg, "nuit") and "bureau" in rooms(pg, ""), "Remove from this group; the room joins the ungrouped ones")
    # a room of no group can be added to one
    q(pg, "[data-group=''] [data-room=cave] [data-action=room-menu]").click()
    ok(q(pg, ".menu .item").all_inner_texts() == ["Add to another group…"], "a room in no group can only be added")
    q(pg, ".menu [data-action=add-room]").click(); q(pg, "select.target").select_option("vide"); q(pg, "[data-action=mover-ok]").click(); settle(pg)
    ok(rooms(pg, "vide") == ["cave"], "added to a group")

    pg.close(); pg = new()

    # ---- reorder rooms
    q(pg, "[data-group=jour] [data-action=group-menu]").click(); q(pg, ".menu [data-action=reorder-rooms]").click()
    ok(n(pg, "[data-group=jour] [data-action=room-earlier]") == len(rooms(pg, "jour")) and n(pg, "[data-group=jour] [data-action=room-menu]") == 0, "arrows replace the room menus while rearranging")
    before = rooms(pg, "jour")
    q(pg, f"[data-group=jour] [data-room={before[-1]}] [data-action=room-earlier]").click(); settle(pg)
    after = rooms(pg, "jour")
    ok(after[-2] == before[-1] and after[-1] == before[-2], "a room moves earlier")
    ok(q(pg, f"[data-group=jour] [data-room={after[0]}] [data-action=room-earlier]").is_disabled(), "the first room cannot move earlier")
    ok(last(pg)[1]["areas"] == after, "the new order is saved")
    q(pg, "[data-action=rooms-done]").click()
    ok(n(pg, "[data-action=room-earlier]") == 0, "Done leaves the mode")

    # ---- reorder groups
    q(pg, "[data-action=page-menu]").click(); q(pg, ".menu [data-action=reorder-groups]").click()
    q(pg, "[data-group=vide] [data-action=group-up]").click(); settle(pg)
    ok(order(pg) == ["nuit", "vide", "jour"] and [g["id"] for g in last(pg)] == ["nuit", "vide", "jour"], "a group moves up and the order is saved")
    ok(q(pg, "[data-group=nuit] [data-action=group-up]").is_disabled() and n(pg, "[data-action=group-menu]") == 0, "limits and no menus while rearranging groups")
    q(pg, "[data-action=groups-done]").click()

    # ---- edit
    q(pg, "[data-group=nuit] [data-action=group-menu]").click(); q(pg, ".menu [data-action=edit-group]").click()
    ok(q(pg, "input.gname").input_value() == "Night" and q(pg, "input.gid").input_value() == "nuit" and q(pg, "input.gicon").input_value() == "mdi:bed", "the dialog shows the group")
    ok(n(pg, "[data-field=aliases] .chip") == 1, "aliases are listed")
    q(pg, "input.gname").fill("Day"); ok(q(pg, "[data-action=dialog-save]").is_disabled(), "a name used by another group is refused")
    q(pg, "input.gname").fill("Night time")
    ok(q(pg, "input.gid").input_value() == "nuit", "the ID never changes")
    q(pg, "[data-field=aliases] [data-alias=Nuit] .chipx").click()
    q(pg, "[data-field=rooms] .chip >> nth=0 >> .chipx").click()
    q(pg, "[data-action=dialog-save]").click(); settle(pg)
    g = [x for x in last(pg) if x["id"] == "nuit"][0]
    ok(g["name"] == "Night time" and g["aliases"] == [] and len(g["areas"]) == 1, "edit saved: renamed, alias and room removed")
    q(pg, "[data-group=nuit] [data-action=group-menu]").click(); q(pg, ".menu [data-action=edit-group]").click()
    q(pg, "[data-action=dialog-close]").click()
    ok(n(pg, ".dialog") == 0, "the dialog can be closed without saving")

    # ---- delete
    q(pg, "[data-group=vide] [data-action=group-menu]").click(); q(pg, ".menu [data-action=delete-group]").click()
    ok(n(pg, "[role=alertdialog]") == 1 and "Empty" in q(pg, "[role=alertdialog]").inner_text(), "deleting asks first")
    q(pg, "[data-action=confirm-cancel]").click()
    ok(n(pg, "[data-group=vide]") == 1, "Cancel keeps the group")
    q(pg, "[data-group=vide] [data-action=group-menu]").click(); q(pg, ".menu [data-action=delete-group]").click(); q(pg, "[data-action=confirm-delete]").click(); settle(pg)
    ok(n(pg, "[data-group=vide]") == 0 and [x["id"] for x in last(pg)] == ["nuit", "jour"], "the group is deleted")
    pg.close()

    # ---- the plan tab still works and does not own the groups
    pg = new()
    pg.locator("css=home-structure-panel >> [data-tab=plan]").click()
    ok(pg.locator("css=home-structure-panel >> .tray").count() == 1 and pg.locator("css=home-structure-panel >> home-structure-groups").count() == 0, "the Plan tab shows the plan")
    pg.close()

    # ---- notice when sensors were taken out; failure shown
    pg = new("?groups=1")
    pg.evaluate("window.__s.prune = true")
    q(pg, "[data-group=jour] [data-room=salon] [data-action=room-menu]").click(); q(pg, ".menu [data-action=remove-room]").click(); settle(pg)
    ok(n(pg, "[data-notice]") == 1, "a notice says sensors were removed")
    pg.close()
    pg = new("?groups=1&fail=groups")
    q(pg, "[data-group=jour] [data-room=salon] [data-action=room-menu]").click(); q(pg, ".menu [data-action=remove-room]").click()
    pg.wait_for_function("document.querySelector('home-structure-panel').shadowRoot.querySelector('home-structure-groups').shadowRoot.querySelector('[data-status]').dataset.status === 'error'")
    ok("nope" in q(pg, ".status").inner_text() and "salon" in rooms(pg, "jour"), "a failed save is shown and the page reloads the saved groups")
    pg.close()

    # ---- French, narrow
    pg = new("?groups=1&lang=fr", w=420, h=800)
    ok("Groupes de pièces" in q(pg, "h1").inner_text() and "2 pièces" in q(pg, "[data-group=nuit] header").inner_text(), "French strings")
    ok(pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "no horizontal scroll at phone width")
    pg.screenshot(path=f"{OUT}/g4-narrow-fr.png")
    q(pg, "[data-action=add-group]").click()
    ok("Créer un groupe" in q(pg, ".dialog header").inner_text() and q(pg, "[data-action=dialog-save]").inner_text() == "Enregistrer", "French dialog")
    pg.screenshot(path=f"{OUT}/g5-dialog-fr.png")
    pg.close()

    ok(not errors, f"no console errors {errors[:3]}")
    b.close()

sys.exit(1 if ok.failed else 0)
