/* ============================================================
   鸣潮 · 面板/背景图编辑台 — frontend (vanilla JS)
   ============================================================ */

const API = "/waves/panel-edit/api";

const TYPE_INFO = {
  card:    { label: "面板图",    short: "PANEL",   color: "var(--type-card)",    preview: "panel" },
  bg:      { label: "MR 背景图", short: "MR/BG",    color: "var(--type-bg)",      preview: "mr" },
  stamina: { label: "MR 立绘",   short: "MR/PILE", color: "var(--type-stamina)", preview: "mr" },
};

const state = {
  meta: null,
  role: "admin",              // "admin" | "guest" — 由 /api/meta 返回
  type: "card",
  folders: [],
  filterText: "",
  selectedCharId: null,
  selectedImage: null,        // {name, hash_id, ...}
  imagesByCharId: {},         // cache: {`${type}|${charId}`: [images]}

  // mode: "browse" | "single-crop" | "batch"
  mode: "browse",
  // 缩略图基准宽度 (px); null = 跟随 CSS 默认 (响应式)
  thumbSize: null,
  // single-crop tmp:
  cropTmp: null,              // {token, suffix, source: {w,h}, current: {w,h}, kind: "upload" | "edit-existing", origin: {char_id,name}? }
  cropRect: null,             // {x,y,w,h} display coords (图像坐标系, 原点=图片左上角)
  cropImgEl: null,
  cropClient: null,           // {w,h} 上次记录的图片显示尺寸, 供窗口缩放校正
  // batch:
  batchItems: [],             // [{token,name,suffix,width,height,size,confirmed?,charId?}]
  batchAllow: false,          // confirm-all checkbox

  renderer: "html",           // for mr preview

  // preview auto-refresh:
  previewSeq: 0,
  previewAuto: (() => { try { return localStorage.getItem("ww.panelEdit.previewAuto") !== "0"; } catch (_) { return true; } })(),
  // 实时裁剪: 关闭后控制框变化不触发 crop + 预览, 需手动点「应用裁剪」
  autoCrop: (() => { try { return localStorage.getItem("ww.panelEdit.autoCrop") !== "0"; } catch (_) { return true; } })(),

  // edit-existing warning dismissed
  editWarnDismissed: false,
};

// ============================================================
// DOM
// ============================================================
const $ = sel => document.querySelector(sel);
const el = (tag, props, ...children) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (v === false || v == null) continue;
    else node.setAttribute(k, v);
  }
  for (const c of children) {
    if (c == null || c === false) continue;
    node.append(c.nodeType ? c : document.createTextNode(c));
  }
  return node;
};

// ============================================================
// API helpers
// ============================================================
async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, { cache: "no-store", ...opts });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch (_) {}
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res;
}
async function apiJson(path, body, method = "POST") {
  return api(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ============================================================
// Toasts
// ============================================================
function toast(msg, kind = "info", timeout = 3500) {
  const t = el("div", { class: `toast is-${kind}` },
    el("div", { class: "toast__msg", text: msg }),
    el("button", { class: "toast__close", "aria-label": "dismiss",
                   onClick: () => t.remove() }, "✕"),
  );
  $("#toasts").append(t);
  if (timeout) setTimeout(() => t.remove(), timeout);
}

// ============================================================
// Lazy thumb loader — IntersectionObserver + 并发限制 + 带退避的重试
// 弱网环境: navigator.connection 报 slow-2g/2g/3g 时压低并发到 2。
// ============================================================
const LazyImages = (() => {
  const queue = [];
  let inflight = 0;

  const conn = (typeof navigator !== "undefined" && navigator.connection) || null;
  const slow = () => conn && /^(slow-2g|2g|3g)$/.test(conn.effectiveType || "");
  const max = () => (slow() ? 2 : 4);
  const MAX_RETRY = 3;
  const BACKOFFS = [800, 2400, 6000]; // ms

  const next = () => {
    while (inflight < max() && queue.length) {
      const node = queue.shift();
      if (!node || !node.isConnected) continue;
      attempt(node);
    }
  };

  const attempt = (node) => {
    const src = node.dataset.src;
    if (!src) return;
    inflight++;
    const tile = node.parentElement;
    tile?.classList.remove("is-error");

    const onLoad = () => {
      cleanup();
      tile?.classList.add("is-loaded");
      done();
    };
    const onError = () => {
      cleanup();
      const tries = (parseInt(node.dataset.tries || "0", 10) | 0) + 1;
      node.dataset.tries = String(tries);
      if (tries < MAX_RETRY) {
        const wait = BACKOFFS[Math.min(tries - 1, BACKOFFS.length - 1)];
        setTimeout(() => {
          if (node.isConnected) queue.push(node);
          done();
        }, wait);
      } else {
        tile?.classList.add("is-error");
        done();
      }
    };
    const cleanup = () => {
      node.removeEventListener("load", onLoad);
      node.removeEventListener("error", onError);
    };
    const done = () => {
      inflight--;
      next();
    };

    node.addEventListener("load", onLoad);
    node.addEventListener("error", onError);
    // 加 cache-bust 仅在重试时避免命中浏览器对失败 URL 的负缓存
    const tries = parseInt(node.dataset.tries || "0", 10) | 0;
    node.src = tries > 0 ? `${src}${src.includes("?") ? "&" : "?"}retry=${tries}` : src;
  };

  const observer = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      const node = e.target;
      observer.unobserve(node);
      queue.push(node);
    }
    next();
  }, { rootMargin: "200px 0px", threshold: 0.01 });

  // 网络从离线变在线时, 把所有失败 tile 挑出来再试一次
  if (typeof window !== "undefined") {
    window.addEventListener("online", () => {
      document.querySelectorAll(".tile.is-error img[data-src]").forEach(img => {
        img.dataset.tries = "0";
        img.parentElement?.classList.remove("is-error");
        queue.push(img);
      });
      next();
    });
  }

  return {
    observe(node) { observer.observe(node); },
    retry(node) {
      node.dataset.tries = "0";
      node.parentElement?.classList.remove("is-error");
      queue.push(node);
      next();
    },
    reset() { queue.length = 0; }
  };
})();

// ============================================================
// META + initial load
// ============================================================
async function loadMeta() {
  state.meta = await api("/meta");
  state.role = state.meta?.role === "guest" ? "guest" : "admin";
  renderTypeTabs();
  renderRoleBadge();
}

function isGuest() { return state.role !== "admin"; }

function renderRoleBadge() {
  const meta = $("#topbarMeta");
  meta.innerHTML = "";
  if (isGuest()) {
    meta.append(
      el("span", { class: "status-dot status-dot--warn" }),
      el("span", { class: "topbar__status", text: "访客 / 只读" }),
      el("button", {
        class: "btn btn--ghost topbar__login",
        title: "以管理员登录",
        onClick: triggerLogin,
      }, "登录"),
    );
  } else {
    meta.append(
      el("span", { class: "status-dot status-dot--ok" }),
      el("span", { class: "topbar__status", text: "管理员 / Basic Auth" }),
    );
  }
}

async function triggerLogin() {
  // 命中需要 admin 的端点; 浏览器自动弹 Basic Auth 对话框。
  try {
    await api("/login");
    toast("已登录", "ok");
    await loadMeta();
    renderCenter();
    renderPreview();
  } catch (e) {
    if (e.status === 429) {
      toast(`登录已锁定: ${e.message}`, "err");
    } else if (e.status === 401) {
      // 用户取消 / 输入错: 浏览器已经弹过了, 这里不再重复提示
      toast("登录失败或已取消", "warn");
    } else {
      toast(`登录异常: ${e.message}`, "err");
    }
  }
}

function renderTypeTabs() {
  const root = $("#typeTabs");
  root.innerHTML = "";
  const order = ["card", "bg", "stamina"];
  for (const k of order) {
    const info = TYPE_INFO[k];
    const tab = el("button", {
      class: "tab" + (state.type === k ? " is-active" : ""),
      role: "tab",
      "aria-selected": String(state.type === k),
      onClick: () => switchType(k),
    },
      el("span", { class: "tab__swatch", style: `background:${info.color}` }),
      info.label,
    );
    root.append(tab);
  }
}

async function switchType(t) {
  if (state.type === t) return;
  state.type = t;
  state.selectedCharId = null;
  state.selectedImage = null;
  state.mode = "browse";
  renderTypeTabs();
  await loadFolders();
  renderCenter();
  renderPreview();
}

async function loadFolders() {
  try {
    const data = await api(`/folders?type=${state.type}`);
    state.folders = data.folders || [];
  } catch (e) {
    toast(`加载文件夹失败: ${e.message}`, "err");
    state.folders = [];
  }
  renderFolders();
}

function renderFolders() {
  const root = $("#folderList");
  root.innerHTML = "";
  const ft = state.filterText.trim().toLowerCase();
  const list = state.folders.filter(f =>
    !ft ||
    f.char_id.toLowerCase().includes(ft) ||
    (f.char_name || "").toLowerCase().includes(ft)
  );
  $("#folderCount").textContent = `${list.length} / ${state.folders.length}`;
  if (!list.length) {
    root.append(el("div", { class: "sidebar__empty",
      text: state.folders.length ? "无匹配文件夹" : "此类型暂无文件夹" }));
    return;
  }
  for (const f of list) {
    const row = el("div", {
      class: "folder" + (state.selectedCharId === f.char_id ? " is-active" : ""),
      role: "button",
      tabindex: "0",
      onClick: () => selectFolder(f.char_id),
      onKeydown: (ev) => { if (ev.key === "Enter") selectFolder(f.char_id); },
    },
      el("span", { class: "folder__id", text: f.char_id }),
      el("span", { class: "folder__name", title: f.char_name, text: f.char_name || "—" }),
      el("span", { class: "folder__count", text: String(f.count) }),
    );
    root.append(row);
  }
}

async function selectFolder(charId) {
  state.selectedCharId = charId;
  state.selectedImage = null;
  state.mode = "browse";
  renderFolders();
  renderCenter();
  renderPreview();
  await loadImages();
}

async function loadImages() {
  if (!state.selectedCharId) return;
  const key = `${state.type}|${state.selectedCharId}`;
  try {
    const data = await api(`/images?type=${state.type}&char_id=${encodeURIComponent(state.selectedCharId)}`);
    state.imagesByCharId[key] = data.images || [];
  } catch (e) {
    toast(`加载图片失败: ${e.message}`, "err");
    state.imagesByCharId[key] = [];
  }
  renderCenter();
}

// ============================================================
// CENTER — head + body (mode-aware)
// ============================================================
function renderCenter() {
  renderCenterHead();
  renderCenterBody();
}

function renderCenterHead() {
  const head = $("#centerHead");
  head.innerHTML = "";

  if (!state.selectedCharId) {
    head.append(
      el("div", { class: "center__title" },
        el("h2", { text: "未选中文件夹" }),
        el("span", { class: "crumb", text: TYPE_INFO[state.type].label }),
      )
    );
    return;
  }

  const folder = state.folders.find(f => f.char_id === state.selectedCharId);
  const charName = folder?.char_name || state.meta?.id2name?.[state.selectedCharId] || "—";
  const info = TYPE_INFO[state.type];

  const titleBlock = el("div", { class: "center__title" },
    el("span", { class: "type-pill" },
      el("span", { class: "swatch", style: `background:${info.color}` }),
      info.short,
    ),
    el("h2", { text: charName }),
    el("span", { class: "crumb" },
      el("b", { text: state.selectedCharId }),
      " · ",
      `${(state.imagesByCharId[`${state.type}|${state.selectedCharId}`] || []).length} 张`
    ),
  );

  const actions = el("div", { class: "center__actions" });

  if (state.mode === "single-crop") {
    actions.append(
      el("button", { class: "btn btn--ghost", onClick: cancelCrop }, "返回"),
    );
  } else if (state.mode === "batch") {
    actions.append(
      buildThumbSizer(),
      el("button", { class: "btn btn--ghost", onClick: () => { state.mode = "browse"; renderCenter(); } }, "返回"),
    );
  } else {
    actions.append(buildThumbSizer());
    if (!isGuest()) {
      actions.append(
        el("button", { class: "btn", onClick: openSingleUpload }, "上传单张"),
        el("button", { class: "btn", onClick: openBatchUpload }, "批量上传"),
      );
    }
  }

  head.append(titleBlock, actions);
}

function renderCenterBody() {
  const body = $("#centerBody");
  body.innerHTML = "";

  if (state.mode === "single-crop") return renderCropper(body);
  if (state.mode === "batch") return renderBatch(body);

  // browse
  if (!state.selectedCharId) {
    body.append(el("div", { class: "empty" },
      el("div", { class: "empty__title", text: "NO FOLDER" }),
      el("div", { text: "选择左侧文件夹开始浏览。" }),
    ));
    return;
  }

  if (!isGuest()) body.append(renderDropzone());

  const key = `${state.type}|${state.selectedCharId}`;
  const images = state.imagesByCharId[key];
  if (!images) {
    body.append(el("div", { class: "empty", text: "加载中…" }));
    return;
  }
  if (!images.length) {
    body.append(el("div", { class: "empty" },
      el("div", { class: "empty__title", text: "EMPTY" }),
      el("div", { text: "此文件夹尚无图片，拖入或点击上方按钮上传。" }),
    ));
    return;
  }

  const grid = el("div", { class: "grid" });
  const isLandscape = state.type === "bg";
  for (const img of images) {
    grid.append(renderTile(img, isLandscape));
  }
  body.append(grid);
}

function renderTile(img, isLandscape) {
  const isSelected = state.selectedImage?.name === img.name;
  const ar = tileAspect(state.type);
  const tile = el("div", {
    class: "tile" + (isLandscape ? " is-landscape" : "") + (isSelected ? " is-selected" : ""),
    style: ar ? `aspect-ratio:${ar}` : null,
    role: "button",
    tabindex: "0",
    "aria-label": `${img.hash_id} ${img.name}`,
    onClick: (e) => {
      // 加载失败时点击 = 重试; 否则 = 选中。
      const tile = e.currentTarget;
      if (tile.classList.contains("is-error")) {
        const i = tile.querySelector("img[data-src]");
        if (i) LazyImages.retry(i);
        return;
      }
      selectImage(img);
    },
    onKeydown: e => { if (e.key === "Enter") selectImage(img); },
  },
    el("div", { class: "tile__skeleton" }),
    (() => {
      const url = `${API}/thumb?type=${state.type}&char_id=${encodeURIComponent(state.selectedCharId)}&name=${encodeURIComponent(img.name)}&size=360&v=${state.meta?.thumb_ver ?? 0}-${img.mtime ?? 0}-${img.size ?? 0}`;
      const i = el("img", { alt: img.hash_id, loading: "lazy", decoding: "async", "data-src": url });
      LazyImages.observe(i);
      return i;
    })(),
    el("div", { class: "tile__menu" },
      el("a", {
        class: "tile-act tile-act--link",
        href: `${API}/image?type=${state.type}&char_id=${encodeURIComponent(state.selectedCharId)}&name=${encodeURIComponent(img.name)}&trim=1&v=${img.mtime ?? 0}-${img.size ?? 0}`,
        download: img.name,
        title: "下载原图",
        "aria-label": "下载原图",
        onClick: e => e.stopPropagation(),
      }, "⤓"),
      !isGuest() && el("button", {
        class: "tile-act",
        title: "编辑裁切",
        "aria-label": "编辑裁切",
        onClick: e => { e.stopPropagation(); editExisting(img); },
      }, "✎"),
      !isGuest() && el("button", {
        class: "tile-act tile-act--danger",
        title: "删除",
        "aria-label": "删除",
        onClick: e => { e.stopPropagation(); deleteImage(img); },
      }, "✕"),
    ),
    el("div", { class: "tile__hash" },
      el("span", { text: img.hash_id }),
      el("span", { class: "meta", text: formatBytes(img.size) }),
    ),
  );
  return tile;
}

function selectImage(img) {
  state.selectedImage = img;
  // re-render only what changed
  renderCenterBody();
  renderPreview();
}

async function deleteImage(img) {
  if (!confirm(`确认删除 ${img.name}? 此操作不可撤销。`)) return;
  try {
    await apiJson("/delete", { type: state.type, char_id: state.selectedCharId, name: img.name });
    toast("已删除", "ok");
    if (state.selectedImage?.name === img.name) state.selectedImage = null;
    await loadImages();
    await loadFolders();
    renderCenter();
    renderPreview();
  } catch (e) {
    toast(`删除失败: ${e.message}`, "err");
  }
}

// ============================================================
// DROPZONE
// ============================================================
function renderDropzone() {
  const dz = el("div", { class: "dropzone" },
    el("div", { class: "dropzone__title", text: "DROP TO UPLOAD" }),
    el("div", { class: "dropzone__sub",
      text: "拖拽图片到此处。单张进入裁剪模式，多张则进入批量暂存。" }),
    el("div", { class: "dropzone__row" },
      el("button", { class: "btn", onClick: openSingleUpload }, "选择单张"),
      el("button", { class: "btn", onClick: openBatchUpload }, "批量选择"),
    ),
  );

  dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("is-hot"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("is-hot"));
  dz.addEventListener("drop", async e => {
    e.preventDefault();
    dz.classList.remove("is-hot");
    const files = [...e.dataTransfer.files].filter(f => f.type.startsWith("image/"));
    if (!files.length) return;
    if (files.length === 1) await uploadSingle(files[0]);
    else await uploadBatch(files);
  });
  return dz;
}

function openSingleUpload() {
  if (!state.selectedCharId) return toast("请先选中文件夹", "warn");
  pickFiles(false, files => {
    if (files[0]) uploadSingle(files[0]);
  });
}

// 选中文件夹 + browse 模式下, 粘贴图片 → 单图裁剪。
function onGlobalPaste(e) {
  if (isGuest()) return;
  if (!state.selectedCharId) return;
  if (state.mode !== "browse") return;
  const items = e.clipboardData?.items;
  if (!items) return;
  for (const it of items) {
    if (it.kind === "file" && (it.type || "").startsWith("image/")) {
      const f = it.getAsFile();
      if (!f) continue;
      e.preventDefault();
      uploadSingle(f);
      return;
    }
  }
}
function openBatchUpload() {
  if (!state.selectedCharId) return toast("请先选中文件夹", "warn");
  pickFiles(true, files => {
    if (files.length === 1) uploadSingle(files[0]);
    else if (files.length > 1) uploadBatch(files);
  });
}
function pickFiles(multiple, cb) {
  const input = el("input", { type: "file", accept: "image/*" });
  if (multiple) input.multiple = true;
  input.addEventListener("change", () => cb([...(input.files || [])]));
  input.click();
}

// ============================================================
// SINGLE UPLOAD + CROPPER
// ============================================================
async function uploadSingle(file) {
  const fd = new FormData();
  fd.append("file", file);
  try {
    const data = await api("/tmp/upload", { method: "POST", body: fd });
    state.cropTmp = {
      token: data.token,
      suffix: data.suffix,
      source: { w: data.width, h: data.height },
      current: { w: data.width, h: data.height },
      kind: "upload",
    };
    state.mode = "single-crop";
    closeMobileDrawers();
    renderCenter();
    renderPreview();
  } catch (e) {
    toast(`上传失败: ${e.message}`, "err");
  }
}

function renderCropper(body) {
  if (state.cropTmp?.kind === "edit-existing" && !state.editWarnDismissed) {
    body.append(el("div", { class: "warn-banner" },
      el("span", { class: "warn-banner__icon", text: "!" }),
      el("div", { class: "warn-banner__msg",
        text: "编辑会覆盖原图并重建索引，无法撤销，请谨慎。" }),
      el("button", { class: "btn btn--ghost",
        onClick: () => { state.editWarnDismissed = true; renderCenterBody(); } }, "知道了"),
    ));
  }

  const tmp = state.cropTmp;
  const readout = el("div", { class: "cropper__readout" },
    el("span", null, el("span", { class: "k", text: "源:" }),
      el("b", { text: `${tmp.source.w}×${tmp.source.h}` })),
    el("span", null, el("span", { class: "k", text: "当前:" }),
      el("b", { id: "cropCurSize", text: `${tmp.current.w}×${tmp.current.h}` })),
    el("span", null, el("span", { class: "k", text: "裁剪 (源像素):" }),
      el("b", { id: "cropRectReadout", text: "—" })),
    el("label", {
      class: "crop-auto",
      title: "关闭后, 拖动控制框不再自动裁剪/刷新预览; 需手动点「应用裁剪」",
    },
      el("input", {
        type: "checkbox",
        ...(state.autoCrop ? { checked: "checked" } : {}),
        onChange: (e) => {
          state.autoCrop = e.target.checked;
          try { localStorage.setItem("ww.panelEdit.autoCrop", state.autoCrop ? "1" : "0"); } catch (_) {}
          if (!state.autoCrop) {
            clearTimeout(_autoCropTimer);
            _autoCropTimer = null;
            syncCropConfirm();
          }
        },
      }),
      el("span", { text: "实时裁剪" }),
    ),
  );

  const bar = el("div", { class: "cropper__bar" },
    readout,
    el("div", { class: "cropper__actions" },
      el("button", { class: "btn", onClick: applyCrop }, "应用裁剪"),
      el("button", { class: "btn", onClick: restoreCrop }, "还原"),
      el("button", { class: "btn", onClick: promptResize }, "缩放"),
      el("button", { id: "cropConfirmBtn", class: "btn btn--primary",
        onClick: tmp.kind === "edit-existing" ? confirmReplace : confirmUpload },
        tmp.kind === "edit-existing" ? "确认覆盖" : "确认上传"),
    ),
  );

  const stage = el("div", { class: "cropper__stage" });
  const wrap = el("div", { class: "cropper__canvas-wrap" });
  const img = el("img", {
    class: "cropper__img",
    src: `${API}/tmp/image?token=${tmp.token}&_=${Date.now()}`,
    onLoad: () => initCropRect(img, wrap),
  });
  state.cropImgEl = img;
  wrap.append(img);
  stage.append(wrap);

  body.append(bar, stage);
}

// 裁剪框贴边时的最小留白(px), 也是 CSS .cropper__canvas-wrap 的初始 padding。
// 框选超出原图时, 该侧 padding 会按超出量动态增大(见 layoutCropper), 形成"往外拉自动外扩"的白色填充预览。
const CROP_FRAME = 12;

// 面板(card)图渲染参数: 自定义图经 resize_and_center 以 contain 方式缩放居中进 PANEL_OUT,
// 「查看面板图」只显示其中 PANEL_VIS 窗口(与后端 card_utils._PANEL_VISIBLE_BOX_LOCAL 对齐)。
const PANEL_OUT = { w: 560, h: 1000 };
const PANEL_VIS = { l: 60, t: 95, r: 500, b: 900 };
// stamina/MR 卡背景容器 (对齐 stamina_card.html .container / 后端 storage._BG_DISPLAY_RATIO)
const MR_CARD = { w: 1150, h: 850 };

// 缩略图框比例 = 该类型在角色卡的实际显示区比例 (card 取 PANEL_VIS 窗口, bg 取背景容器)
function tileAspect(type) {
  if (type === "card") return (PANEL_VIS.r - PANEL_VIS.l) / (PANEL_VIS.b - PANEL_VIS.t);
  if (type === "bg") return MR_CARD.w / MR_CARD.h;
  return null;
}

// 计算「查看面板图」实际可见窗口, 返回相对"裁剪框左上角"的显示坐标(裁剪框即将来保存的图)。
// 裁剪框尺寸变化时实时重算 → 虚线随裁剪框联动。无法计算时返回 null。
// 复刻后端 card_utils.resize_and_center: W×H 以 contain 缩放居中进 560×1000, 仅显示窗口 (60,95,500,900)。
// 直接用裁剪框显示尺寸计算: 显示是源的等比缩放, 可见窗口占框的"比例"与源坐标系一致, 故结果等价。
function panelVisibleRectInCrop(W, H) {
  if (!(W > 0) || !(H > 0)) return null;
  const f = (W > H) ? (PANEL_OUT.w / W) : (PANEL_OUT.h / H);
  const pasteX = (PANEL_OUT.w - W * f) / 2;
  const pasteY = (PANEL_OUT.h - H * f) / 2;
  // 可见窗口映射回框坐标, 并 clamp 到框内(超出部分是居中留白/白色填充, 不算可见内容)
  const l = Math.max(0, Math.min((PANEL_VIS.l - pasteX) / f, W));
  const t = Math.max(0, Math.min((PANEL_VIS.t - pasteY) / f, H));
  const r = Math.max(0, Math.min((PANEL_VIS.r - pasteX) / f, W));
  const b = Math.max(0, Math.min((PANEL_VIS.b - pasteY) / f, H));
  if (r <= l || b <= t) return null;
  return { x: l, y: t, w: r - l, h: b - t };
}

function initCropRect(img, wrap) {
  // Initialize crop rect to full image (display coords)
  const w = img.clientWidth;
  const h = img.clientHeight;
  state.cropRect = { x: 0, y: 0, w, h };
  state.cropClient = { w, h };  // 记录当前显示尺寸, 供窗口缩放时按比例校正
  drawCropRect(wrap);
  updateRectReadout();
}

function drawCropRect(wrap) {
  wrap.querySelector(".cropper__rect")?.remove();
  wrap.querySelector(".cropper__visbox")?.remove();
  if (!state.cropRect) return;

  // card: visbox(面板可见区) 作为主控件, rect 仅作为虚线轮廓; 其它类型直接拖 rect
  const isCard = state.type === "card";
  const rect = el("div", {
    class: "cropper__rect" + (isCard ? " cropper__rect--passive" : ""),
  });
  if (!isCard) {
    for (const h_ of ["nw", "n", "ne", "e", "se", "s", "sw", "w"]) {
      rect.append(el("span", { class: `handle h-${h_}`, "data-h": h_ }));
    }
    rect.addEventListener("pointerdown", ev => startDrag(ev, wrap, rect));
  }
  wrap.append(rect);

  if (isCard) {
    const vis = el("div", { class: "cropper__visbox cropper__visbox--active" });
    for (const h_ of ["nw", "n", "ne", "e", "se", "s", "sw", "w"]) {
      vis.append(el("span", { class: `handle h-${h_}`, "data-h": h_ }));
    }
    vis.addEventListener("pointerdown", ev => startVisDrag(ev, wrap, vis));
    wrap.append(vis);
  }

  layoutCropper(wrap);
}

// 统一布局: 按框选超出量动态设置 wrap padding(白色外扩区), 再据此定位裁剪框与可见区引导框。
function layoutCropper(wrap) {
  const r = state.cropRect;
  const img = state.cropImgEl;
  if (!wrap || !r || !img) return;
  const iw = img.clientWidth, ih = img.clientHeight;
  // 框选超出原图时, 对应侧 padding 按超出量动态增大(白色填充预览); 未超出侧保持最小留白。
  // 用 ceil 保证 padL ≥ -r.x, 框左/上边不会溢出白色填充区(亚像素也不漏)。
  const padL = Math.max(CROP_FRAME, Math.ceil(-r.x));
  const padT = Math.max(CROP_FRAME, Math.ceil(-r.y));
  const padR = Math.max(CROP_FRAME, Math.ceil(r.x + r.w - iw));
  const padB = Math.max(CROP_FRAME, Math.ceil(r.y + r.h - ih));
  wrap.style.padding = `${padT}px ${padR}px ${padB}px ${padL}px`;

  // 图片左上角位于 padding 盒内 (padL, padT); 裁剪框用图像坐标系, 叠加该偏移。
  const rect = wrap.querySelector(".cropper__rect");
  if (rect) {
    rect.style.left = `${padL + r.x}px`;
    rect.style.top = `${padT + r.y}px`;
    rect.style.width = `${r.w}px`;
    rect.style.height = `${r.h}px`;
  }
  // 可见区引导: 相对裁剪框计算(框=将来保存的图), 故随裁剪框实时联动; 再叠加框在 wrap 内的位置。
  const vis = wrap.querySelector(".cropper__visbox");
  if (vis) {
    const v = panelVisibleRectInCrop(r.w, r.h);
    if (v) {
      vis.style.display = "";
      vis.style.left = `${padL + r.x + v.x}px`;
      vis.style.top = `${padT + r.y + v.y}px`;
      vis.style.width = `${v.w}px`;
      vis.style.height = `${v.h}px`;
    } else {
      vis.style.display = "none";
    }
  }
}

// 浏览器窗口缩放时图片显示尺寸会变, 按比例校正 cropRect 并重新布局, 否则裁剪框与图片错位。
function onCropperResize() {
  if (state.mode !== "single-crop") return;
  const img = state.cropImgEl;
  if (!img || !state.cropRect || !state.cropClient) return;
  const nw = img.clientWidth, nh = img.clientHeight;
  const ow = state.cropClient.w, oh = state.cropClient.h;
  if (!ow || !oh) { state.cropClient = { w: nw, h: nh }; return; }
  if (nw === ow && nh === oh) return;
  const rx = nw / ow, ry = nh / oh;
  const r = state.cropRect;
  state.cropRect = { x: r.x * rx, y: r.y * ry, w: r.w * rx, h: r.h * ry };
  state.cropClient = { w: nw, h: nh };
  layoutCropper(img.parentElement);
  updateRectReadout();
}
window.addEventListener("resize", onCropperResize);

function startDrag(ev, wrap, rect) {
  if (isCropBusy()) { ev.preventDefault(); return; }
  ev.preventDefault();

  const target = ev.target;
  const isHandle = target.classList.contains("handle");
  const direction = target.dataset.h;
  const start = { sx: ev.clientX, sy: ev.clientY, ...state.cropRect };
  const maxW = state.cropImgEl.clientWidth;
  const maxH = state.cropImgEl.clientHeight;

  // pointer capture: 保证手指/光标移出元素后仍持续收 move 事件。
  try { rect.setPointerCapture(ev.pointerId); } catch (_) {}

  let pending = null;
  const flush = () => {
    pending = null;
    layoutCropper(wrap);
    updateRectReadout();
  };

  const move = e => {
    const dx = e.clientX - start.sx;
    const dy = e.clientY - start.sy;
    // 允许框选超出原图: 各边最多向外扩展一个图尺寸(即输出 ≤ 3×), 越界部分由后端白色填充
    const MIN = 8;
    const minBX = -maxW, maxBX = 2 * maxW;
    const minBY = -maxH, maxBY = 2 * maxH;
    let { x, y, w, h } = start;
    if (!isHandle) {
      // 整体拖动: 平移后 clamp 位置, 尺寸不变
      x = Math.min(Math.max(start.x + dx, minBX), maxBX - w);
      y = Math.min(Math.max(start.y + dy, minBY), maxBY - h);
    } else {
      // 拉伸: 只移动被拖的边, 对边固定(避免触边时把对边一起带动)
      let left = start.x, top = start.y, right = start.x + start.w, bottom = start.y + start.h;
      if (direction.includes("w")) left = Math.min(Math.max(left + dx, minBX), right - MIN);
      if (direction.includes("e")) right = Math.max(Math.min(right + dx, maxBX), left + MIN);
      if (direction.includes("n")) top = Math.min(Math.max(top + dy, minBY), bottom - MIN);
      if (direction.includes("s")) bottom = Math.max(Math.min(bottom + dy, maxBY), top + MIN);
      x = left; y = top; w = right - left; h = bottom - top;
    }
    state.cropRect = { x, y, w, h };
    if (pending == null) pending = requestAnimationFrame(flush);
  };

  const cleanup = () => {
    rect.removeEventListener("pointermove", move);
    rect.removeEventListener("pointerup", onUp);
    rect.removeEventListener("pointercancel", cleanup);
    try { rect.releasePointerCapture(ev.pointerId); } catch (_) {}
    if (pending != null) {
      cancelAnimationFrame(pending);
      flush();
    }
  };
  // 真·释放 → 落库; pointercancel (浏览器取消手势) → 只清监听器, rect 保留位置。
  const onUp = () => { cleanup(); scheduleAutoCrop(); };

  rect.addEventListener("pointermove", move);
  rect.addEventListener("pointerup", onUp);
  rect.addEventListener("pointercancel", cleanup);
}

// card 类型: 拖 visbox 反推 cropRect。visbox 比例锁 = (PANEL_VIS.r-l):(PANEL_VIS.b-t) = 440:805。
// rect 始终是 visbox 的 PANEL_OUT 比例外扩 (f = 805/vh, W=560/f, H=1000/f), 即标准 contain 居中嵌入。
function startVisDrag(ev, wrap, visEl) {
  if (isCropBusy()) { ev.preventDefault(); return; }
  ev.preventDefault();

  const target = ev.target;
  const isHandle = target.classList.contains("handle");
  const direction = target.dataset.h || "";

  const cur = panelVisibleRectInCrop(state.cropRect.w, state.cropRect.h);
  if (!cur) return;
  const start = {
    sx: ev.clientX, sy: ev.clientY,
    x: state.cropRect.x + cur.x,
    y: state.cropRect.y + cur.y,
    w: cur.w, h: cur.h,
  };

  const VIS_W = PANEL_VIS.r - PANEL_VIS.l;  // 440
  const VIS_H = PANEL_VIS.b - PANEL_VIS.t;  // 805
  const VIS_RATIO = VIS_W / VIS_H;
  const MIN_VH = 24;

  const applyVis = (vx, vy, vw, vh) => {
    const f = VIS_H / vh;
    state.cropRect = {
      x: vx - PANEL_VIS.l / f,
      y: vy - PANEL_VIS.t / f,
      w: PANEL_OUT.w / f,
      h: PANEL_OUT.h / f,
    };
  };

  try { visEl.setPointerCapture(ev.pointerId); } catch (_) {}

  let pending = null;
  const flush = () => {
    pending = null;
    layoutCropper(wrap);
    updateRectReadout();
  };

  const move = e => {
    const dx = e.clientX - start.sx;
    const dy = e.clientY - start.sy;
    if (!isHandle) {
      applyVis(start.x + dx, start.y + dy, start.w, start.h);
    } else {
      let nw = start.w, nh = start.h;
      if (direction.includes("w")) nw = start.w - dx;
      if (direction.includes("e")) nw = start.w + dx;
      if (direction.includes("n")) nh = start.h - dy;
      if (direction.includes("s")) nh = start.h + dy;
      if (direction.length === 2) {
        // 角拖: 取主导轴 (变化更大者) 决定另一轴
        const wFromH = nh * VIS_RATIO;
        if (Math.abs(nw - start.w) >= Math.abs(wFromH - start.w)) nh = nw / VIS_RATIO;
        else nw = wFromH;
      } else if (direction === "w" || direction === "e") {
        nh = nw / VIS_RATIO;
      } else {
        nw = nh * VIS_RATIO;
      }
      nh = Math.max(MIN_VH, nh);
      nw = nh * VIS_RATIO;

      // 锚: 不含拖动方向的边固定
      let nx = start.x, ny = start.y;
      if (direction.includes("w")) nx = start.x + start.w - nw;
      else if (!direction.includes("e")) nx = start.x + (start.w - nw) / 2;
      if (direction.includes("n")) ny = start.y + start.h - nh;
      else if (!direction.includes("s")) ny = start.y + (start.h - nh) / 2;
      applyVis(nx, ny, nw, nh);
    }
    if (pending == null) pending = requestAnimationFrame(flush);
  };

  const cleanup = () => {
    visEl.removeEventListener("pointermove", move);
    visEl.removeEventListener("pointerup", onUp);
    visEl.removeEventListener("pointercancel", cleanup);
    try { visEl.releasePointerCapture(ev.pointerId); } catch (_) {}
    if (pending != null) {
      cancelAnimationFrame(pending);
      flush();
    }
  };
  const onUp = () => { cleanup(); scheduleAutoCrop(); };

  visEl.addEventListener("pointermove", move);
  visEl.addEventListener("pointerup", onUp);
  visEl.addEventListener("pointercancel", cleanup);
}

// 拖拽结束后等待 IDLE_MS 静止再落库, 节流连续微调。
const _AUTO_CROP_IDLE_MS = 800;
let _autoCropTimer = null;
let _cropInflight = false;

// 裁剪结果落库前禁用「确认」, 防止保存到旧 tmp 丢失最新一次裁剪。
function isCropBusy() { return _autoCropTimer != null || _cropInflight; }
function syncCropConfirm() {
  const busy = isCropBusy();
  const btn = document.getElementById("cropConfirmBtn");
  if (btn) btn.disabled = busy;
  const rect = document.querySelector(".cropper__rect");
  if (rect) rect.classList.toggle("is-busy", busy);
  const vis = document.querySelector(".cropper__visbox");
  if (vis) vis.classList.toggle("is-busy", busy);
  const actions = document.querySelector(".cropper__actions");
  if (actions) actions.classList.toggle("is-busy", busy);
}

function scheduleAutoCrop() {
  if (!state.autoCrop) return;
  clearTimeout(_autoCropTimer);
  _autoCropTimer = setTimeout(async () => {
    _autoCropTimer = null;
    if (_cropInflight) {
      // 在途时排队再触发一次, 保证最新一次操作一定被应用
      _autoCropTimer = setTimeout(scheduleAutoCrop, 200);
      syncCropConfirm();
      return;
    }
    await applyCrop({ silent: true });
  }, _AUTO_CROP_IDLE_MS);
  syncCropConfirm();
}

function displayToSourceRect(rect) {
  const img = state.cropImgEl;
  if (!img) return null;
  const sx = img.naturalWidth / img.clientWidth;
  const sy = img.naturalHeight / img.clientHeight;
  return {
    // 允许负坐标(框选越过原图左/上边界), 越界部分后端白色填充
    x: Math.round(rect.x * sx),
    y: Math.round(rect.y * sy),
    w: Math.max(1, Math.round(rect.w * sx)),
    h: Math.max(1, Math.round(rect.h * sy)),
  };
}

function updateRectReadout() {
  const node = document.getElementById("cropRectReadout");
  if (!node || !state.cropRect) return;
  const s = displayToSourceRect(state.cropRect);
  node.textContent = s ? `${s.x},${s.y} ${s.w}×${s.h}` : "—";
}

async function applyCrop(opts = {}) {
  const { silent = false } = opts;
  if (_cropInflight) return;
  const tmp = state.cropTmp;
  if (!tmp) return;
  const src = displayToSourceRect(state.cropRect);
  if (!src) return;
  // src 是相对 current 的坐标; 叠加 current 在原图内的 offset → 原图绝对坐标, 始终从原图裁
  const off = tmp.offset || { x: 0, y: 0 };
  const abs = { x: off.x + src.x, y: off.y + src.y, w: src.w, h: src.h };
  _cropInflight = true;
  syncCropConfirm();
  try {
    const r = await apiJson("/tmp/crop", { token: tmp.token, ...abs });
    tmp.offset = { x: abs.x, y: abs.y };
    tmp.current = { w: r.width, h: r.height };
    const sizeEl = document.getElementById("cropCurSize");
    if (sizeEl) sizeEl.textContent = `${r.width}×${r.height}`;
    refreshCropImg();
    await waitCropImgLoad();
    triggerPreview(true);
    if (!silent) toast("已裁剪", "ok", 1800);
  } catch (e) {
    toast(`裁剪失败: ${e.message}`, "err");
  } finally {
    _cropInflight = false;
    syncCropConfirm();
  }
}

async function restoreCrop() {
  if (_cropInflight) return;
  const tmp = state.cropTmp;
  if (!tmp) return;
  _cropInflight = true;
  syncCropConfirm();
  try {
    const r = await apiJson("/tmp/restore", { token: tmp.token });
    tmp.offset = { x: 0, y: 0 };
    tmp.current = { w: r.width, h: r.height };
    document.getElementById("cropCurSize").textContent = `${r.width}×${r.height}`;
    refreshCropImg();
    await waitCropImgLoad();
    triggerPreview();
    toast("已还原", "ok", 1800);
  } catch (e) {
    toast(`还原失败: ${e.message}`, "err");
  } finally {
    _cropInflight = false;
    syncCropConfirm();
  }
}

function refreshCropImg() {
  if (!state.cropImgEl) return;
  state.cropImgEl.src = `${API}/tmp/image?token=${state.cropTmp.token}&_=${Date.now()}`;
}

function waitCropImgLoad() {
  return new Promise((resolve) => {
    const img = state.cropImgEl;
    if (!img) return resolve();
    if (img.complete && img.naturalWidth) return resolve();
    const cleanup = () => {
      img.removeEventListener("load", onLoad);
      img.removeEventListener("error", onErr);
    };
    const onLoad = () => { cleanup(); resolve(); };
    const onErr = () => { cleanup(); resolve(); };
    img.addEventListener("load", onLoad);
    img.addEventListener("error", onErr);
  });
}

async function promptResize() {
  if (isCropBusy()) return;
  const tmp = state.cropTmp;
  if (!tmp) return;
  const raw = window.prompt("缩放倍率 (0.05 - 8.0, 例如 0.5 / 1.5)", "1.0");
  if (raw == null) return;
  const scale = parseFloat(raw);
  if (!Number.isFinite(scale) || scale < 0.05 || scale > 8) {
    toast("倍率超出范围", "warn");
    return;
  }
  if (Math.abs(scale - 1) < 1e-3) return;
  _cropInflight = true;
  syncCropConfirm();
  try {
    const r = await apiJson("/tmp/resize", { token: tmp.token, scale });
    tmp.current = { w: r.width, h: r.height };
    tmp.source = { w: r.source_width, h: r.source_height };
    if (tmp.offset) {
      tmp.offset = {
        x: Math.round(tmp.offset.x * scale),
        y: Math.round(tmp.offset.y * scale),
      };
    }
    renderCenterBody();
    syncCropConfirm();
    await waitCropImgLoad();
    triggerPreview(true);
    toast(`已缩放 ${r.width}×${r.height}`, "ok");
  } catch (e) {
    toast(`缩放失败: ${e.message}`, "err");
  } finally {
    _cropInflight = false;
    syncCropConfirm();
  }
}

function _resetCropState() {
  state.cropTmp = null;
  state.cropRect = null;
  state.cropImgEl = null;
  state.cropClient = null;
  state.editWarnDismissed = false;
  clearTimeout(_autoCropTimer);
  _autoCropTimer = null;
  _cropInflight = false;
}

async function cancelCrop() {
  const tmp = state.cropTmp;
  // 来自批量暂存的 item: 取消裁剪只是回到暂存区, 不丢弃 tmp 文件。
  const fromBatch = tmp?.fromBatch === true;
  if (tmp && !fromBatch) {
    try { await apiJson("/tmp/discard", { token: tmp.token }); } catch (_) {}
  }
  _resetCropState();
  state.mode = (fromBatch && state.batchItems.length) ? "batch" : "browse";
  renderCenter();
  renderPreview();
}

async function confirmUpload() {
  const tmp = state.cropTmp;
  if (!tmp) return;
  const fromBatch = tmp.fromBatch === true;
  try {
    const r = await apiJson("/confirm", {
      token: tmp.token, type: state.type, char_id: state.selectedCharId,
    });
    toast(`已上传 ${r.hash_id}`, "ok");
    if (fromBatch) {
      state.batchItems = state.batchItems.filter(x => x.token !== tmp.token);
    }
    _resetCropState();
    state.selectedImage = { name: r.name, hash_id: r.hash_id };
    state.mode = (fromBatch && state.batchItems.length) ? "batch" : "browse";
    await loadImages();
    await loadFolders();
    renderCenter();
    renderPreview();
  } catch (e) {
    toast(`确认失败: ${e.message}`, "err");
  }
}

async function confirmReplace() {
  const tmp = state.cropTmp;
  if (!tmp || tmp.kind !== "edit-existing") return;
  if (!confirm("确认用裁剪后的内容覆盖原图? 此操作不可撤销。")) return;
  try {
    const r = await apiJson("/replace-existing", {
      token: tmp.token, type: state.type,
      char_id: state.selectedCharId,
      name: tmp.origin.name,
    });
    toast(`已覆盖 ${r.hash_id}`, "ok");
    _resetCropState();
    state.mode = "browse";
    state.selectedImage = { name: r.name, hash_id: r.hash_id };
    await loadImages();
    renderCenter();
    renderPreview();
  } catch (e) {
    toast(`覆盖失败: ${e.message}`, "err");
  }
}

// ============================================================
// EDIT EXISTING (load original into a fresh tmp)
// ============================================================
async function editExisting(img) {
  try {
    const url = `${API}/image?type=${state.type}&char_id=${encodeURIComponent(state.selectedCharId)}&name=${encodeURIComponent(img.name)}&v=${img.mtime ?? 0}-${img.size ?? 0}`;
    const blob = await (await fetch(url, { cache: "no-store" })).blob();
    const fd = new FormData();
    fd.append("file", new File([blob], img.name, { type: blob.type || "image/jpeg" }));
    const r = await api("/tmp/upload", { method: "POST", body: fd });
    state.cropTmp = {
      token: r.token,
      suffix: r.suffix,
      source: { w: r.width, h: r.height },
      current: { w: r.width, h: r.height },
      kind: "edit-existing",
      origin: { char_id: state.selectedCharId, name: img.name },
    };
    state.editWarnDismissed = false;
    state.mode = "single-crop";
    closeMobileDrawers();
    renderCenter();
    renderPreview();
  } catch (e) {
    toast(`无法编辑: ${e.message}`, "err");
  }
}

// ============================================================
// BATCH
// ============================================================
async function uploadBatch(files) {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  try {
    const data = await api("/tmp/upload-batch", { method: "POST", body: fd });
    state.batchItems = data.items || [];
    state.batchAllow = false;
    state.mode = "batch";
    renderCenter();
    renderPreview();
  } catch (e) {
    toast(`批量上传失败: ${e.message}`, "err");
  }
}

function renderBatch(body) {
  body.append(el("div", { class: "warn-banner" },
    el("span", { class: "warn-banner__icon", text: "!" }),
    el("div", { class: "warn-banner__msg",
      text: "批量上传不会逐张确认效果，请确认无误后再点击「全部确认上传」。" }),
  ));

  body.append(el("div", { class: "batch-bar" },
    el("div", { class: "batch-bar__msg" },
      el("span", { class: "icon", text: state.batchItems.length }),
      `共 ${state.batchItems.length} 张暂存于临时区。`
    ),
    el("div", { class: "row" },
      el("label", { class: "batch-bar__check" },
        el("input", {
          type: "checkbox",
          ...(state.batchAllow ? { checked: "checked" } : {}),
          onChange: e => { state.batchAllow = e.target.checked; renderCenterBody(); },
        }),
        "我已确认风险",
      ),
      el("button", {
        class: "btn btn--primary",
        ...((!state.batchAllow || !state.batchItems.length) ? { disabled: "disabled" } : {}),
        onClick: confirmAllBatch,
      }, "全部确认上传"),
    ),
  ));

  if (!state.batchItems.length) {
    body.append(el("div", { class: "empty",
      text: "暂存区空。" }));
    return;
  }

  const grid = el("div", { class: "batch-grid" });
  for (const it of state.batchItems) {
    const card = el("div", { class: "staging-card" },
      el("img", {
        loading: "lazy",
        decoding: "async",
        src: `${API}/tmp/image?token=${it.token}`,
        alt: it.name,
      }),
      el("div", { class: "staging-card__meta" },
        el("span", { text: `${it.width}×${it.height}` }),
        el("span", { text: formatBytes(it.size) }),
      ),
      el("div", { class: "staging-card__row" },
        el("button", { class: "btn",
          onClick: () => editBatchItem(it) }, "裁剪"),
        el("button", { class: "btn btn--danger",
          onClick: () => discardBatchItem(it) }, "丢弃"),
      ),
    );
    grid.append(card);
  }
  body.append(grid);
}

async function editBatchItem(it) {
  // 暂存 item → single-crop; cancel/confirm 会用 fromBatch 决定是否回到 batch。
  state.cropTmp = {
    token: it.token,
    suffix: it.suffix,
    source: { w: it.width, h: it.height },
    current: { w: it.width, h: it.height },
    kind: "upload",
    fromBatch: true,
  };
  state.mode = "single-crop";
  closeMobileDrawers();
  renderCenter();
  renderPreview();
}

async function discardBatchItem(it) {
  try { await apiJson("/tmp/discard", { token: it.token }); } catch (_) {}
  state.batchItems = state.batchItems.filter(x => x.token !== it.token);
  renderCenterBody();
}

async function confirmAllBatch() {
  if (!state.batchAllow || !state.batchItems.length) return;
  let ok = 0, fail = 0;
  for (const it of state.batchItems.slice()) {
    try {
      await apiJson("/confirm", {
        token: it.token, type: state.type, char_id: state.selectedCharId,
      });
      state.batchItems = state.batchItems.filter(x => x.token !== it.token);
      ok++;
    } catch (_) { fail++; }
  }
  toast(`确认完成 — 成功 ${ok} 张${fail ? ` / 失败 ${fail}` : ""}`, fail ? "warn" : "ok");
  if (!state.batchItems.length) state.mode = "browse";
  await loadImages();
  await loadFolders();
  renderCenter();
  renderPreview();
}

// ============================================================
// PREVIEW
// ============================================================
function renderPreview() {
  const head = $("#previewControls");
  head.innerHTML = "";
  const titleEl = $("#previewTitle");
  const subEl = $("#previewSub");
  const foot = $("#previewFoot");
  foot.innerHTML = "";

  // 访客模式: 完全不渲染预览, 不触发任何后端 CPU 占用。
  if (isGuest()) {
    titleEl.textContent = "预览";
    subEl.textContent = "访客模式 / 仅浏览";
    setPreviewSrc(null, false);
    const ph = $("#previewPlaceholder");
    if (ph) {
      ph.querySelector(".preview__placeholder-title").textContent = "GUEST MODE";
      ph.querySelector(".preview__placeholder-sub").textContent =
        "访客只能浏览图片列表，预览功能需登录后开启。";
    }
    foot.append(
      el("span", { class: "muted", text: "访客模式 — 不渲染预览" }),
      el("button", { class: "btn btn--ghost", onClick: triggerLogin }, "登录解锁"),
    );
    return;
  }

  // decide what to render
  const needPreview = (
    (state.mode === "browse" && state.selectedImage && state.selectedCharId) ||
    (state.mode === "single-crop" && state.cropTmp && state.selectedCharId)
  );

  if (state.type === "card") {
    titleEl.textContent = "角色面板预览";
  } else {
    titleEl.textContent = "MR 预览";
    head.append(buildRendererToggle());
  }

  // sub
  if (state.mode === "browse" && state.selectedImage) {
    subEl.textContent = `${state.selectedImage.hash_id} · ${state.selectedImage.name}`;
  } else if (state.mode === "single-crop" && state.cropTmp) {
    subEl.textContent = `tmp · ${state.cropTmp.token.slice(0, 8)}…`;
  } else {
    subEl.textContent = "未选中";
  }

  // refresh controls
  if (needPreview) {
    head.append(buildPreviewAutoToggle());
    head.append(el("button", { class: "btn btn--ghost", title: "刷新预览",
      onClick: () => triggerPreview(true, true) }, "刷新"));
  }

  if (!needPreview) {
    setPreviewSrc(null, false);
    foot.append(el("span", { class: "muted", text: "无预览。" }));
    return;
  }

  // foot meta
  if (state.mode === "browse" && state.selectedImage) {
    const img = state.selectedImage;
    foot.append(
      el("span", null, "id ", el("b", { text: img.hash_id })),
      el("span", null, "size ", el("b", { text: formatBytes(img.size) })),
      el("span", null, "char ", el("b", { text: state.selectedCharId })),
    );
  } else if (state.mode === "single-crop" && state.cropTmp) {
    const t = state.cropTmp;
    foot.append(
      el("span", null, "tmp ", el("b", { text: t.token.slice(0, 12) })),
      el("span", null, "src ", el("b", { text: `${t.source.w}×${t.source.h}` })),
      el("span", null, "now ", el("b", { text: `${t.current.w}×${t.current.h}` })),
    );
  }

  if (!state.previewAuto) {
    foot.append(el("span", { class: "muted", text: "自动刷新已关闭 · 点「刷新」更新" }));
  }
  triggerPreview();
}

function buildPreviewAutoToggle() {
  return el("label", { class: "preview-auto", title: "连续调整时关闭可避免反复重渲染闪烁；关闭后需手动点「刷新」" },
    el("input", {
      type: "checkbox",
      ...(state.previewAuto ? { checked: "checked" } : {}),
      onChange: e => {
        state.previewAuto = e.target.checked;
        try { localStorage.setItem("ww.panelEdit.previewAuto", state.previewAuto ? "1" : "0"); } catch (_) {}
        clearTimeout(previewTimer);
        renderPreview();
      },
    }),
    el("span", { text: "自动刷新" }),
  );
}

function buildRendererToggle() {
  const seg = el("div", { class: "seg", role: "tablist", "aria-label": "渲染器" });
  for (const r of ["html", "pil"]) {
    seg.append(el("button", {
      class: state.renderer === r ? "is-active" : "",
      role: "tab",
      "aria-selected": String(state.renderer === r),
      onClick: () => {
        if (state.renderer === r) return;
        state.renderer = r;
        renderPreview();
      },
    }, r.toUpperCase()));
  }
  return seg;
}

function buildPreviewUrl() {
  if (state.mode === "browse" && state.selectedImage && state.selectedCharId) {
    const p = new URLSearchParams({
      type: state.type,
      char_id: state.selectedCharId,
      name: state.selectedImage.name,
      renderer: state.renderer,
    });
    return `${API}/preview?${p.toString()}`;
  }
  if (state.mode === "single-crop" && state.cropTmp && state.selectedCharId) {
    const p = new URLSearchParams({
      type: state.type,
      char_id: state.selectedCharId,
      token: state.cropTmp.token,
      renderer: state.renderer,
    });
    return `${API}/preview-tmp?${p.toString()}`;
  }
  return null;
}

function setPreviewSrc(url, loading) {
  const vp = $("#previewViewport");
  const img = $("#previewImg");
  const overlay = $("#previewOverlay");
  if (!url) {
    img.removeAttribute("src");
    vp.classList.remove("has-image");
    overlay.classList.remove("is-on");
    return;
  }
  if (loading) overlay.classList.add("is-on");
  img.onload = () => {
    overlay.classList.remove("is-on");
    vp.classList.add("has-image");
  };
  img.onerror = () => {
    overlay.classList.remove("is-on");
    vp.classList.remove("has-image");
    toast("预览渲染失败", "err");
  };
  img.src = url;
}

let previewTimer = null;
function triggerPreview(force = false, manual = false) {
  // 访客一律不发预览请求, 防止任何路径意外触达 /api/preview。
  if (isGuest()) return setPreviewSrc(null, false);
  // 关闭自动刷新: 仅手动「刷新」(manual) 触发渲染
  if (!manual && !state.previewAuto) return;
  const url = buildPreviewUrl();
  if (!url) return setPreviewSrc(null, false);
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {
    state.previewSeq++;
    setPreviewSrc(`${url}&_=${state.previewSeq}`, true);
  }, force ? 0 : 60);
}

// ============================================================
// utilities
// ============================================================
function formatBytes(n) {
  if (n == null) return "—";
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`;
  return `${(n / 1024 / 1024).toFixed(2)}MB`;
}

// debounce input
function debounce(fn, ms) {
  let t = null;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// ============================================================
// Layout — resizable side / preview panes + mobile drawers
// ============================================================
const LAYOUT_KEY = "ww.panelEdit.layout.v1";

function loadLayout() {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return;
    const v = JSON.parse(raw);
    if (typeof v.side === "number") setPaneWidth("--side-w", v.side, 200, 480);
    if (typeof v.preview === "number") setPaneWidth("--preview-w", v.preview, 280, 720);
    if (typeof v.thumb === "number") setThumbSize(v.thumb);
  } catch (_) {}
}

function saveLayout() {
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({
      side: parsePx(getComputedStyle(document.documentElement).getPropertyValue("--side-w")),
      preview: parsePx(getComputedStyle(document.documentElement).getPropertyValue("--preview-w")),
      thumb: state.thumbSize,
    }));
  } catch (_) {}
}

const THUMB_MIN = 80;
const THUMB_MAX = 280;

function setThumbSize(px) {
  if (px == null) {
    state.thumbSize = null;
    document.documentElement.style.removeProperty("--tile-min");
    return;
  }
  const v = Math.max(THUMB_MIN, Math.min(THUMB_MAX, Math.round(px)));
  state.thumbSize = v;
  document.documentElement.style.setProperty("--tile-min", `${v}px`);
}

function buildThumbSizer() {
  const slider = el("input", {
    type: "range",
    min: String(THUMB_MIN),
    max: String(THUMB_MAX),
    step: "4",
    value: String(state.thumbSize ?? 148),
    "aria-label": "缩略图大小",
    title: "拖动调整缩略图大小; 双击重置为响应式默认",
    onInput: e => {
      setThumbSize(parseInt(e.target.value, 10));
      const v = sizer.querySelector(".thumb-sizer__val");
      if (v) v.textContent = `${state.thumbSize}px`;
    },
    onChange: () => saveLayout(),
    onDblclick: () => {
      setThumbSize(null);
      saveLayout();
      // 重渲染让 slider 反映默认值
      renderCenterHead();
    },
  });
  const sizer = el("div", { class: "thumb-sizer", role: "group" },
    el("span", { class: "thumb-sizer__ico", text: "▦" }),
    slider,
    el("span", { class: "thumb-sizer__val",
      text: state.thumbSize == null ? "auto" : `${state.thumbSize}px` }),
  );
  return sizer;
}

function parsePx(s) { const n = parseFloat(s); return Number.isFinite(n) ? n : 0; }

function setPaneWidth(varName, px, min, max) {
  const v = Math.max(min, Math.min(max, Math.round(px)));
  document.documentElement.style.setProperty(varName, `${v}px`);
}

function bindResizer(elNode, varName, dir, min, max) {
  let startX = 0, startW = 0, dragging = false;
  const onDown = (ev) => {
    ev.preventDefault();
    dragging = true;
    elNode.classList.add("is-active");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    startX = ev.clientX;
    startW = parsePx(getComputedStyle(document.documentElement).getPropertyValue(varName));
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp, { once: true });
  };
  const onMove = (ev) => {
    if (!dragging) return;
    const delta = (ev.clientX - startX) * dir;
    setPaneWidth(varName, startW + delta, min, max);
  };
  const onUp = () => {
    dragging = false;
    elNode.classList.remove("is-active");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    document.removeEventListener("pointermove", onMove);
    saveLayout();
  };
  elNode.addEventListener("pointerdown", onDown);
  elNode.addEventListener("dblclick", () => {
    setPaneWidth(varName, varName === "--side-w" ? 296 : 440, min, max);
    saveLayout();
  });
  elNode.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const cur = parsePx(getComputedStyle(document.documentElement).getPropertyValue(varName));
    const step = e.shiftKey ? 32 : 8;
    const delta = (e.key === "ArrowRight" ? 1 : -1) * dir * step;
    setPaneWidth(varName, cur + delta, min, max);
    saveLayout();
  });
}

function closeMobileDrawers() {
  $("#sidebar").classList.remove("is-open");
  $("#previewPane").classList.remove("is-open");
  $("#scrim").classList.remove("is-on");
}

function setupLayout() {
  loadLayout();
  bindResizer($("#resizerSide"), "--side-w", +1, 200, 480);
  bindResizer($("#resizerPreview"), "--preview-w", -1, 280, 720);

  // mobile drawers
  const sidebar = $("#sidebar");
  const preview = $("#previewPane");
  const scrim = $("#scrim");
  $("#mobileMenu").addEventListener("click", () => {
    const wasOpen = sidebar.classList.contains("is-open");
    closeMobileDrawers();
    if (!wasOpen) {
      sidebar.classList.add("is-open");
      scrim.classList.add("is-on");
    }
  });
  $("#mobilePreview").addEventListener("click", () => {
    const wasOpen = preview.classList.contains("is-open");
    closeMobileDrawers();
    if (!wasOpen) {
      preview.classList.add("is-open");
      scrim.classList.add("is-on");
    }
  });
  scrim.addEventListener("click", closeMobileDrawers);
  // tap inside sidebar list closes drawer when picking a folder (mobile UX)
  sidebar.addEventListener("click", (e) => {
    if (window.matchMedia("(max-width: 820px)").matches && e.target.closest(".folder")) {
      // 等本次 click 触发完 selectFolder 后再收
      setTimeout(closeMobileDrawers, 60);
    }
  });
}


// ============================================================
// Init
// ============================================================
async function init() {
  setupLayout();
  document.addEventListener("paste", onGlobalPaste);
  // type tab tabs render after meta.
  $("#folderFilter").addEventListener("input", debounce(e => {
    state.filterText = e.target.value;
    renderFolders();
  }, 80));

  try {
    await loadMeta();
  } catch (e) {
    if (e.status === 503) {
      $("#topbarMeta").innerHTML = "";
      $("#topbarMeta").append(
        el("span", { class: "status-dot status-dot--err" }),
        el("span", { class: "topbar__status", text: "未启用 / 配置 WavesPanelEditPassword" }),
      );
      $("#centerBody").append(el("div", { class: "empty" },
        el("div", { class: "empty__title", text: "DISABLED" }),
        el("div", { text: "请在 WutheringWavesConfig 中设置 WavesPanelEditPassword 后重启或刷新。" }),
      ));
      return;
    }
    toast(`初始化失败: ${e.message}`, "err");
    return;
  }

  await loadFolders();
  renderCenter();
  renderPreview();
}

document.addEventListener("DOMContentLoaded", init);
