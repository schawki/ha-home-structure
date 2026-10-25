import { css } from "lit";

/** The look shared by the pages that imitate Home Assistant's Areas page: sections, cards, menus, dialogs, fields. */
export const pageCss = css`
    :host { display: block; padding: 8px 16px 96px; box-sizing: border-box; color: var(--primary-text-color); }
    svg { fill: currentColor; flex: none; }
    .msg { padding: 24px; } .muted { color: var(--secondary-text-color); font-size: .85rem; } .empty { padding: 24px 8px; } .warn { color: var(--error-color, #db4437); }
    .head { display: flex; justify-content: flex-end; align-items: center; min-height: 40px; }
    .grow { flex: 1; }
    .status { position: fixed; left: 24px; bottom: 20px; z-index: 12; padding: 8px 14px; border-radius: 8px; background: var(--card-background-color); border: 1px solid var(--divider-color); font-size: .85rem; color: var(--secondary-text-color); box-shadow: 0 2px 8px rgba(0,0,0,.25); }
    .status.idle, .status:empty { display: none; } .status.error { color: var(--error-color, #db4437); font-weight: 600; }
    .notice { background: var(--secondary-background-color); border-radius: 8px; padding: 4px 8px 4px 14px; font-size: .9rem; display: flex; align-items: center; gap: 8px; justify-content: space-between; }
    /* sections and cards, like the floors of the Areas page */
    .group { margin: 0 0 22px; }
    .group header { display: flex; align-items: center; gap: 8px; min-height: 40px; }
    .group header ha-icon { --mdc-icon-size: 18px; color: var(--secondary-text-color); }
    .group header h2 { margin: 0; font-size: .85rem; font-weight: 400; color: var(--secondary-text-color); }
    .cards { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; padding-top: 4px; }
    .card { width: 180px; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; overflow: hidden; box-sizing: border-box; }
    .picture { height: 100px; display: flex; align-items: center; justify-content: center; background: var(--secondary-background-color); color: var(--primary-text-color); }
    .picture ha-icon { --mdc-icon-size: 40px; }
    .info { padding: 8px 8px 14px 16px; min-height: 66px; box-sizing: border-box; }
    .line { display: flex; align-items: center; justify-content: space-between; gap: 4px; min-height: 40px; }
    .line strong { font-size: 1rem; font-weight: 400; line-height: 1.2; overflow-wrap: anywhere; }
    .info small { display: block; color: var(--secondary-text-color); font-size: .75rem; padding-right: 8px; margin-top: 2px; }
    .menuwrap { position: relative; display: inline-flex; }
    .iconbtn, .chipx { display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px; padding: 0; background: none; border: 0; border-radius: 50%; color: var(--secondary-text-color); cursor: pointer; }
    .iconbtn:hover { background: var(--secondary-background-color); } .iconbtn svg { width: 24px; height: 24px; }
    .sortable { cursor: grab; touch-action: none; user-select: none; -webkit-user-select: none; }
    .grip { color: var(--secondary-text-color); font-size: 1.2rem; letter-spacing: -3px; padding: 6px 10px; border-radius: 6px; cursor: grab; } .grip:focus-visible { outline: 2px solid var(--primary-color); }
    .card.dragging, .group.dragging { opacity: .55; box-shadow: 0 6px 18px rgba(0,0,0,.35); border-color: var(--primary-color); }
    .group.compact { margin: 6px 0; } .group.compact header { padding: 4px 8px 4px 16px; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; }
    /* menus */
    .scrim { position: fixed; inset: 0; z-index: 20; }
    .menu { position: absolute; right: 0; top: 100%; z-index: 21; min-width: 250px; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; box-shadow: 0 6px 24px rgba(0,0,0,.4); padding: 6px 0; overflow: hidden; }
    .menu hr { border: 0; border-top: 1px solid var(--divider-color); margin: 6px 0; }
    .item { display: flex; align-items: center; gap: 16px; width: 100%; text-align: left; font: inherit; background: none; border: 0; color: var(--primary-text-color); padding: 12px 20px; cursor: pointer; }
    .item svg { color: var(--secondary-text-color); } .item:hover { background: var(--secondary-background-color); } .item.danger, .item.danger svg { color: var(--error-color, #db4437); }
    .menu.picker { right: auto; left: 0; max-height: 300px; overflow-y: auto; } .menu.picker .item { padding: 10px 20px; } .menu.picker small { color: var(--secondary-text-color); }
    .fab { position: fixed; right: 20px; bottom: 20px; z-index: 10; display: inline-flex; align-items: center; gap: 8px; font: inherit; font-weight: 500; background: var(--primary-color); color: var(--text-primary-color, #fff); border: 0; border-radius: 16px; height: 56px; padding: 0 20px 0 16px; cursor: pointer; box-shadow: 0 3px 10px rgba(0,0,0,.4); }
    /* dialogs */
    .overlay { position: fixed; inset: 0; z-index: 30; background: rgba(0,0,0,.55); display: flex; align-items: flex-start; justify-content: center; overflow-y: auto; padding: 24px 12px; box-sizing: border-box; }
    .dialog { width: 100%; max-width: 580px; background: var(--ha-dialog-surface-background, var(--mdc-theme-surface, var(--card-background-color))); color: var(--primary-text-color); border-radius: 28px; padding: 16px 24px 20px; box-sizing: border-box; box-shadow: 0 10px 40px rgba(0,0,0,.5); }
    .dialog.small { max-width: 400px; margin-top: 15vh; }
    .dialog header { display: flex; align-items: center; gap: 12px; min-height: 56px; margin-left: -8px; } .dialog header h2 { margin: 0; font-size: 1.4rem; font-weight: 400; }
    .idrow { padding: 8px 16px 10px; } .idlabel { font-size: 1rem; } .gid { color: var(--secondary-text-color); font-size: .9rem; min-height: 1.2em; }
    .field { position: relative; display: block; margin: 12px 0 4px; background: color-mix(in srgb, var(--primary-text-color) 8%, var(--card-background-color)); border-radius: 4px 4px 0 0; border-bottom: 1px solid var(--secondary-text-color); }
    .field:focus-within { border-bottom: 2px solid var(--primary-color); } .field:focus-within .flabel { color: var(--primary-color); }
    .flabel { position: absolute; left: 16px; top: 8px; font-size: .75rem; color: var(--secondary-text-color); pointer-events: none; }
    .field input, .field select { display: block; width: 100%; box-sizing: border-box; background: none; border: 0; outline: none; color: var(--primary-text-color); font: inherit; padding: 26px 16px 8px; min-height: 56px; appearance: none; -webkit-appearance: none; }
    .field select option { background: var(--card-background-color); }
    .field.withicon { display: flex; align-items: center; } .field.withicon input { flex: 1; padding-left: 0; } .field.withicon .flabel { left: 56px; }
    .lead { width: 56px; display: inline-flex; justify-content: center; color: var(--secondary-text-color); flex: none; } .field.withicon .iconbtn.clear { margin-right: 4px; }
    .selectfield .caret { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); pointer-events: none; color: var(--secondary-text-color); display: inline-flex; }
    .helper { font-size: .75rem; color: var(--secondary-text-color); padding: 4px 16px 0; } .helper.indent { padding-bottom: 8px; }
    ha-icon-picker { display: block; margin: 12px 0; }
    .dialog h3 { margin: 22px 0 10px; font-size: 1.25rem; font-weight: 400; color: var(--primary-text-color); text-transform: none; letter-spacing: 0; }
    .text { margin: 0 0 12px; line-height: 1.45; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
    .chip { display: inline-flex; align-items: center; gap: 8px; height: 32px; padding: 0 4px 0 12px; border-radius: 16px; border: 1px solid var(--divider-color); font-size: .9rem; } .chip ha-icon { --mdc-icon-size: 20px; color: var(--secondary-text-color); }
    .chipx { width: 28px; height: 28px; color: var(--primary-text-color); } .chipx svg { width: 18px; height: 18px; }
    .tonal { display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 20px 0 14px; border: 0; border-radius: 20px; background: color-mix(in srgb, var(--primary-color) 18%, var(--card-background-color)); color: var(--primary-color); font: inherit; font-weight: 500; cursor: pointer; }
    .aliasrow { display: flex; align-items: center; gap: 8px; } .aliasrow .field { flex: 1; }
    .expansion { margin-top: 24px; border: 1px solid var(--divider-color); border-radius: 12px; }
    .exphead { display: flex; width: 100%; align-items: center; justify-content: space-between; background: none; border: 0; color: var(--primary-text-color); font: inherit; font-weight: 500; padding: 14px 16px; cursor: pointer; }
    .chev { display: inline-flex; transition: transform .15s; transform: rotate(180deg); } .chev.open { transform: none; }
    .expbody { padding: 0 16px 16px; } .sensorbox { margin-top: 8px; } .sensortitle { font-size: 1rem; margin: 10px 0 0; }
    .sensors { list-style: none; margin: 8px 0; padding: 0 16px; font-size: .9rem; } .sensors.readonly li { padding: 4px 0; color: var(--secondary-text-color); }
    label.check { display: flex; gap: 8px; align-items: center; padding: 4px 0; }
    footer { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-top: 26px; }
    .textbtn { background: none; border: 0; color: var(--primary-color); font: inherit; font-weight: 500; padding: 10px 14px; border-radius: 20px; cursor: pointer; }
    .filled { font: inherit; font-weight: 500; background: var(--primary-color); color: var(--text-primary-color, #fff); border: 0; border-radius: 20px; padding: 10px 24px; cursor: pointer; }
    .filled:disabled { background: color-mix(in srgb, var(--primary-text-color) 12%, transparent); color: color-mix(in srgb, var(--primary-text-color) 38%, transparent); cursor: default; } .filled.danger { background: var(--error-color, #db4437); }
  
    /* shared by the floors and groups views */
    .card.clickable { cursor: pointer; } .card.clickable:hover { border-color: var(--primary-color); }
    .picture { background-size: cover; background-position: center; }
    .fabwrap { position: fixed; right: 20px; bottom: 20px; z-index: 10; } .fabwrap .fab { position: static; } .menu.up { top: auto; bottom: calc(100% + 8px); right: 0; }
    .line .iconbtn + .menuwrap { margin-left: -8px; }
`;

/** Paths of the Material Design Icons used by those pages (inline, so nothing has to be loaded). */
export const ICON = {
  close: "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z",
  dots: "M12,16A2,2 0 0,1 14,18A2,2 0 0,1 12,20A2,2 0 0,1 10,18A2,2 0 0,1 12,16M12,10A2,2 0 0,1 14,12A2,2 0 0,1 12,14A2,2 0 0,1 10,12A2,2 0 0,1 12,10M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4Z",
  pencil: "M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z",
  delete: "M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z",
  plus: "M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z",
  minus: "M19,13H5V11H19V13Z",
  arrow: "M4,11V13H16L10.5,18.5L11.92,19.92L19.84,12L11.92,4.08L10.5,5.5L16,11H4Z",
  sort: "M10,13V11H18V13H10M10,19V17H14V19H10M10,7V5H22V7H10M6,17H8.5L5,20.5L1.5,17H4V7H1.5L5,3.5L8.5,7H6V17Z",
  caret: "M7,10L12,15L17,10H7Z",
  chevron: "M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z",
  playlistPlus: "M3,16H10V14H3M18,14V10H16V14H12V16H16V20H18V16H22V14M14,6H3V8H14M14,10H3V12H14V10Z",
};
