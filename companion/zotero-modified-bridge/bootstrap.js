const STATUS_ROUTE = "/api/users/:userID/zotero-modified/statuses";
const STYLES_ROUTE = "/api/users/:userID/zotero-modified/styles";
const CONTEXT_ROUTE = "/api/users/:userID/zotero-modified/context";
const RENDER_ROUTE = "/api/users/:userID/zotero-modified/render";
const NAVIGATE_ROUTE = "/api/users/:userID/zotero-modified/navigate";
const ITEM_MERGE_ROUTE = "/api/users/:userID/zotero-modified/items/merge";
const ROUTES = [
  STATUS_ROUTE,
  STYLES_ROUTE,
  CONTEXT_ROUTE,
  RENDER_ROUTE,
  NAVIGATE_ROUTE,
  ITEM_MERGE_ROUTE,
];
let bridgeVersion = "unknown";

function jsonResponse(status, value) {
  return [status, "application/json", JSON.stringify(value, null, 2)];
}

function textResponse(status, value) {
  return [status, "text/plain", String(value)];
}

function errorResponse(status, code, message, retryable = false, details = undefined) {
  return jsonResponse(status, {
    error: code,
    message,
    retryable,
    ...(details === undefined ? {} : { details }),
  });
}

function validateHexColor(value) {
  return typeof value === "string" && /^#[0-9A-Fa-f]{6}$/.test(value);
}

function normalizeStringArray(value, { max = 20, itemMax = 100 } = {}) {
  if (!Array.isArray(value) || value.length > max) return null;
  const result = [];
  for (let entry of value) {
    if (typeof entry !== "string") return null;
    entry = entry.trim().normalize();
    if (!entry || entry.length > itemMax || result.includes(entry)) return null;
    result.push(entry);
  }
  return result;
}

function mainWindow() {
  return Zotero.getMainWindow?.() || null;
}

// Private/internal Zotero Reader surface. Keep isolated and feature-detect before use.
// Verified against the supported Zotero 10.0.x line.
function getActiveReader() {
  const win = mainWindow();
  if (!win?.Zotero_Tabs || win.Zotero_Tabs.selectedType !== "reader") return null;
  if (typeof Zotero.Reader?.getByTabID !== "function") return null;
  try {
    return Zotero.Reader.getByTabID(win.Zotero_Tabs.selectedID) || null;
  }
  catch (error) {
    Zotero.logError(error);
    return null;
  }
}

async function waitForReaderView(reader) {
  await reader?._initPromise;
  await reader?._internalReader?._primaryView?.initializedPromise;
}

async function itemByKey(libraryID, key) {
  if (typeof key !== "string" || !key.trim()) return null;
  return await Zotero.Items.getByLibraryAndKeyAsync(libraryID, key.trim());
}

function itemField(item, field) {
  try {
    return item?.getField(field) || null;
  }
  catch (_) {
    return null;
  }
}

function itemRecord(item) {
  return {
    key: item.key,
    itemType: item.itemType,
    title: itemField(item, "title"),
  };
}

function readerCapabilities(view, type) {
  const annotationFromSDT = typeof view?.createAnnotationFromSDT === "function";
  const pdfAnnotations = type === "pdf" && annotationFromSDT;
  return {
    sdt: typeof Zotero.SDT?.getReader === "function",
    createAnnotationFromSDT: annotationFromSDT,
    highlight: pdfAnnotations,
    underline: pdfAnnotations,
  };
}

async function activeReaderRecord() {
  const reader = getActiveReader();
  if (!reader) return { active: false };

  await waitForReaderView(reader);
  const attachment = Zotero.Items.get(reader.itemID) || await Zotero.Items.getAsync(reader.itemID);
  if (!attachment) return { active: false };

  const parentID = attachment.parentItemID || attachment.parentID;
  const parent = parentID ? (Zotero.Items.get(parentID) || await Zotero.Items.getAsync(parentID)) : null;
  const view = reader?._internalReader?._primaryView;
  const type = reader.type || attachment.attachmentReaderType || null;
  let page = null;
  if (type === "pdf") {
    try {
      page = view?._iframeWindow?.PDFViewerApplication?.pdfViewer?.currentPageNumber || null;
    }
    catch (_) {
      page = null;
    }
  }
  return {
    active: true,
    type,
    attachmentKey: attachment.key,
    parentItemKey: parent?.key || null,
    page: Number.isInteger(page) ? page : null,
    editable: typeof attachment.isEditable === "function"
      ? !!attachment.isEditable() && !attachment.deleted && !parent?.deleted
      : false,
    capabilities: readerCapabilities(view, type),
  };
}

function parseBody(endpoint, requestData) {
  let body;
  try {
    body = endpoint._parseJSONBody(requestData.data);
  }
  catch (_) {
    const error = new Error("Request body must contain valid JSON");
    error.bridgeStatus = 400;
    error.bridgeCode = "invalid-request";
    throw error;
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    const error = new Error("Request body must be a JSON object");
    error.bridgeStatus = 400;
    error.bridgeCode = "invalid-request";
    throw error;
  }
  return body;
}

function internalError(error, message = "Unexpected Zotero Modified Bridge error") {
  if (Number.isInteger(error?.bridgeStatus)) {
    return errorResponse(
      error.bridgeStatus,
      error.bridgeCode || "invalid-request",
      error.message || "The request is invalid."
    );
  }
  Zotero.logError(error);
  return errorResponse(500, "internal-error", message, true);
}

function coloredTags(libraryID) {
  return Array.from(Zotero.Tags.getColors(libraryID), ([name, value]) => ({
    name,
    color: value.color,
    position: value.position,
  })).sort((a, b) => a.position - b.position);
}

function statusEndpointClass() {
  return class ModifiedStatuses extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["GET", "PUT", "DELETE"];

    async run(requestData) {
      try {
      let { libraryID, method, searchParams } = requestData;
      if (method === "GET") {
        let all = coloredTags(libraryID);
        return jsonResponse(200, {
          bridge: "zotero-modified-bridge",
          version: bridgeVersion,
          coloredTags: all,
          statuses: all.filter((entry) => entry.name.startsWith("/")),
        });
      }

      if (method === "PUT") {
        let body = parseBody(this, requestData);
        let name = typeof body.name === "string" ? body.name.trim().normalize() : "";
        let color = typeof body.color === "string" ? body.color : "";
        let position = Number.isInteger(body.position) ? body.position : undefined;
        if (!name) return textResponse(400, "Tag name is required");
        if (!/^#[0-9A-Fa-f]{6}$/.test(color)) {
          return textResponse(400, "Color must use #RRGGBB syntax");
        }
        if (position !== undefined && position < 0) {
          return textResponse(400, "Position cannot be negative");
        }
        await Zotero.Tags.setColor(libraryID, name, color, position);
        return jsonResponse(200, { name, color, position });
      }

      let name = (searchParams.get("name") || "").trim().normalize();
      if (!name) return textResponse(400, "Query parameter 'name' is required");
      if (searchParams.get("deleteTag") === "1") {
        let tagID = Zotero.Tags.getID(name);
        if (tagID) await Zotero.Tags.removeFromLibrary(libraryID, tagID);
      }
      else {
        await Zotero.Tags.setColor(libraryID, name, false);
      }
      return [204, "text/plain", ""];
      }
      catch (error) {
        Zotero.logError(error);
        return textResponse(400, error.message || error);
      }
    }
  };
}

async function styleRecord(style, includeCSL = false) {
  let record = {
    id: style.styleID,
    title: style.title,
    updated: style.updated,
    hidden: !!style.hidden,
    source: style.source || null,
  };
  if (includeCSL && style.path) {
    record.csl = await Zotero.File.getContentsAsync(style.path);
  }
  return record;
}

function stylesEndpointClass() {
  return class ModifiedStyles extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["GET", "POST", "DELETE"];

    async run(requestData) {
      try {
      let { method, searchParams } = requestData;
      if (method === "GET") {
        let id = searchParams.get("id");
        if (id) {
          let style = Zotero.Styles.get(id, true);
          return style ? jsonResponse(200, await styleRecord(style, true)) : textResponse(404, "Not found");
        }
        let records = [];
        for (let style of Zotero.Styles.getVisible()) {
          records.push(await styleRecord(style));
        }
        return jsonResponse(200, records);
      }

      if (method === "POST") {
        let body = parseBody(this, requestData);
        if (typeof body.csl !== "string" || !body.csl.trim()) {
          return textResponse(400, "CSL text is required");
        }
        await Zotero.Styles.validate(body.csl);
        let installed = await Zotero.Styles.install(
          { string: body.csl },
          typeof body.origin === "string" ? body.origin : "Codex",
          true
        );
        return jsonResponse(200, installed);
      }

      let id = searchParams.get("id");
      if (!id) return textResponse(400, "Query parameter 'id' is required");
      let style = Zotero.Styles.get(id, true);
      if (!style) return textResponse(404, "Not found");
      await style.remove();
      return [204, "text/plain", ""];
      }
      catch (error) {
        Zotero.logError(error);
        return textResponse(400, error.message || error);
      }
    }
  };
}

function contextEndpointClass() {
  return class ModifiedContext extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["GET"];

    async run(requestData) {
      try {
        const win = mainWindow();
        const pane = win?.ZoteroPane;
        let selectedCollections = [];
        let selectedItems = [];
        if (pane) {
          if (typeof pane.getSelectedCollections === "function") {
            selectedCollections = pane.getSelectedCollections(false) || [];
          }
          if (typeof pane.getSelectedItems === "function") {
            selectedItems = pane.getSelectedItems(false, { libraryTabOnly: true }) || [];
          }
        }
        const reader = await activeReaderRecord();
        return jsonResponse(200, {
          bridge: "zotero-modified-bridge",
          version: bridgeVersion,
          activeTab: {
            id: win?.Zotero_Tabs?.selectedID || null,
            type: win?.Zotero_Tabs?.selectedType || null,
          },
          library: {
            selectedCollections: selectedCollections.map((collection) => ({
              key: collection.key,
              name: collection.name,
              libraryID: collection.libraryID,
            })),
            selectedItems: selectedItems.slice(0, 200).map(itemRecord),
          },
          reader,
        });
      }
      catch (error) {
        return internalError(error);
      }
    }
  };
}

function renderEndpointClass() {
  return class ModifiedRender extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["POST"];

    async run(requestData) {
      try {
        const body = parseBody(this, requestData);
        if (!Array.isArray(body.itemKeys) || body.itemKeys.length < 1 || body.itemKeys.length > 100
          || !body.itemKeys.every((key) => typeof key === "string" && key.trim())) {
          return errorResponse(400, "invalid-item-keys", "itemKeys must contain 1–100 item keys");
        }
        if (typeof body.style !== "string" || !body.style.trim()) {
          return errorResponse(400, "invalid-style", "style is required");
        }
        if (!["citation", "bibliography"].includes(body.mode)) {
          return errorResponse(400, "invalid-mode", "mode must be citation or bibliography");
        }
        if (body.locale !== undefined && body.locale !== "" && (typeof body.locale !== "string"
          || !/^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$/.test(body.locale))) {
          return errorResponse(400, "invalid-locale", "locale must be a BCP-47-like value");
        }

        const styleID = body.style.trim();
        const style = Zotero.Styles.get(styleID, true);
        if (!style) return errorResponse(404, "style-not-found", "The requested CSL style is not installed.");

        const items = [];
        for (let key of body.itemKeys) {
          const item = await itemByKey(requestData.libraryID, key);
          if (!item) return errorResponse(404, "item-not-found", `Item '${key}' was not found.`);
          if (item.isNote?.()) {
            return errorResponse(422, "item-not-renderable", `Item '${key}' is a note.`);
          }
          items.push(item);
        }

        const format = {
          mode: "bibliography",
          contentType: "",
          id: styleID,
          locale: body.locale || "",
        };
        const result = Zotero.QuickCopy.getContentFromItems(
          items,
          format,
          null,
          body.mode === "citation"
        );
        if (!result || typeof result !== "object") {
          return errorResponse(422, "render-unavailable", "Zotero could not render these items.", true);
        }
        return jsonResponse(200, {
          mode: body.mode,
          style: styleID,
          itemKeys: body.itemKeys.map((key) => key.trim()),
          text: result.text || "",
          html: result.html || "",
        });
      }
      catch (error) {
        return internalError(error, "Zotero could not render the requested items.");
      }
    }
  };
}

function navigateEndpointClass() {
  return class ModifiedNavigate extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["POST"];

    async run(requestData) {
      try {
        const body = parseBody(this, requestData);
        if (!["reveal-item", "open-attachment", "open-annotation"].includes(body.action)) {
          return errorResponse(400, "invalid-action", "action must be reveal-item, open-attachment, or open-annotation");
        }
        if (typeof body.itemKey !== "string" || !body.itemKey.trim()) {
          return errorResponse(400, "invalid-item-key", "itemKey is required");
        }
        const itemKey = body.itemKey.trim();
        const item = await itemByKey(requestData.libraryID, itemKey);
        if (!item) return errorResponse(404, "item-not-found", `Item '${itemKey}' was not found.`);

        if (body.action === "reveal-item") {
          const pane = mainWindow()?.ZoteroPane;
          if (typeof pane?.selectItem !== "function") {
            return errorResponse(501, "capability-unavailable", "Zotero item selection is unavailable.", true);
          }
          await pane.selectItem(item.id);
        }
        else if (body.action === "open-attachment") {
          if (!item.isAttachment?.()) {
            return errorResponse(422, "invalid-item-type", "open-attachment requires an attachment item.");
          }
          if (typeof Zotero.Reader?.open !== "function") {
            return errorResponse(501, "capability-unavailable", "Zotero Reader is unavailable.", true);
          }
          await Zotero.Reader.open(item.id);
        }
        else {
          if (!item.isAnnotation?.()) {
            return errorResponse(422, "invalid-item-type", "open-annotation requires an annotation item.");
          }
          const parentID = item.parentItemID || item.parentID;
          const parent = parentID ? (Zotero.Items.get(parentID) || await Zotero.Items.getAsync(parentID)) : null;
          if (!parent?.isAttachment?.()) {
            return errorResponse(422, "invalid-annotation-parent", "The annotation parent attachment is unavailable.");
          }
          if (typeof Zotero.Reader?.open !== "function") {
            return errorResponse(501, "capability-unavailable", "Zotero Reader is unavailable.", true);
          }
          await Zotero.Reader.open(parent.id, { annotationID: item.key });
        }
        return jsonResponse(200, {
          ok: true,
          action: body.action,
          requested: itemKey,
          opened: itemKey,
        });
      }
      catch (error) {
        return internalError(error, "Zotero could not perform the requested navigation.");
      }
    }
  };
}

function nativeMergeItems() {
  if (typeof ChromeUtils === "undefined" || typeof ChromeUtils.importESModule !== "function") return null;
  try {
    const module = ChromeUtils.importESModule("chrome://zotero/content/mergeItems.mjs");
    return typeof module?.mergeItems === "function" ? module.mergeItems : null;
  }
  catch (error) {
    Zotero.logError(error);
    return null;
  }
}

function itemMergeKey(value) {
  return typeof value === "string" ? value.trim() : "";
}

function exactVersionMap(value, keys) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const actualKeys = Object.keys(value).sort();
  const expectedKeys = [...keys].sort();
  return actualKeys.length === expectedKeys.length
    && actualKeys.every((key, index) => key === expectedKeys[index])
    && keys.every((key) => Number.isInteger(value[key]) && value[key] >= 0);
}

function mergeableItem(item) {
  return !!item && !item.deleted
    && typeof item.isTopLevelItem === "function" && item.isTopLevelItem()
    && typeof item.isRegularItem === "function" && item.isRegularItem();
}

function itemMergeSnapshot(items) {
  const collect = (method) => [...new Set(items.flatMap((item) => (
    typeof item[method] === "function" ? item[method]() : []
  )))];
  return {
    collectionIDs: collect("getCollections"),
    attachmentIDs: collect("getAttachments"),
    noteIDs: collect("getNotes"),
  };
}

function missingMergeValues(actual, expected) {
  const values = new Set(actual);
  return expected.filter((value) => !values.has(value));
}

function itemMergeEndpointClass() {
  return class ModifiedItemMerge extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["POST"];

    async run(requestData) {
      try {
        const body = parseBody(this, requestData);
        const masterKey = itemMergeKey(body.master);
        const otherKeys = Array.isArray(body.others)
          ? body.others.map(itemMergeKey)
          : null;
        if (!masterKey || !otherKeys || otherKeys.length < 1 || otherKeys.length > 20
          || otherKeys.some((key) => !key)) {
          return errorResponse(400, "invalid-merge-items", "masterKey and 1–20 otherKeys are required");
        }
        const keys = [masterKey, ...otherKeys];
        if (new Set(keys).size !== keys.length) {
          return errorResponse(400, "duplicate-item-keys", "masterKey and otherKeys must be unique");
        }
        if (!exactVersionMap(body.expectedVersions, keys)) {
          return errorResponse(400, "invalid-expected-versions", "expectedVersions must exactly cover all item keys");
        }
        const library = Zotero.Libraries.get(requestData.libraryID);
        if (!library || library.editable === false) {
          return errorResponse(423, "library-read-only", "The Zotero library is not editable.");
        }

        const items = [];
        for (const key of keys) {
          const item = await itemByKey(requestData.libraryID, key);
          if (!item) return errorResponse(404, "item-not-found", `Item '${key}' was not found.`);
          if (!mergeableItem(item)) {
            return errorResponse(422, "item-not-mergeable", `Item '${key}' must be a top-level regular item.`);
          }
          if (typeof item.isEditable === "function" && !item.isEditable()) {
            return errorResponse(423, "item-read-only", `Item '${key}' is not editable.`);
          }
          if (Number(item.clientVersion) !== body.expectedVersions[key]) {
            return errorResponse(
              412,
              "item-version-changed",
              `Item '${key}' changed since the preview.`,
              true,
              { key, expectedVersion: body.expectedVersions[key], actualVersion: item.clientVersion }
            );
          }
          items.push(item);
        }

        const beforeMerge = itemMergeSnapshot(items);
        const mergeItems = nativeMergeItems();
        if (!mergeItems) {
          return errorResponse(501, "capability-unavailable", "Zotero's native item merge module is unavailable.", true);
        }
        await mergeItems(items[0], items.slice(1));

        const master = await itemByKey(requestData.libraryID, masterKey);
        if (!master || master.deleted) {
          return errorResponse(500, "merge-readback-failed", "The merged master item could not be read back.", true);
        }
        const afterMerge = itemMergeSnapshot([master]);
        const missingCollections = missingMergeValues(afterMerge.collectionIDs, beforeMerge.collectionIDs);
        const missingAttachments = missingMergeValues(afterMerge.attachmentIDs, beforeMerge.attachmentIDs);
        const missingNotes = missingMergeValues(afterMerge.noteIDs, beforeMerge.noteIDs);
        if (missingCollections.length || missingAttachments.length || missingNotes.length) {
          return errorResponse(
            500,
            "merge-readback-failed",
            "The merged master item did not retain every collection or child item.",
            true,
            { missingCollections, missingAttachments, missingNotes }
          );
        }
        const trashed = [];
        for (const key of otherKeys) {
          const item = await itemByKey(requestData.libraryID, key);
          if (!item || !item.deleted) {
            return errorResponse(
              500,
              "merge-readback-failed",
              `Merged item '${key}' was not marked deleted by Zotero.`,
              true,
              { key }
            );
          }
          trashed.push(key);
        }
        return jsonResponse(200, {
          merged: true,
          master: { key: master.key, version: master.clientVersion },
          trashed,
        });
      }
      catch (error) {
        return internalError(error, "Zotero could not merge the items.");
      }
    }
  };
}

async function startup(data) {
  bridgeVersion = data && data.version ? String(data.version) : "unknown";
  await Zotero.initializationPromise;
  Zotero.Server.Endpoints[STATUS_ROUTE] = statusEndpointClass();
  Zotero.Server.Endpoints[STYLES_ROUTE] = stylesEndpointClass();
  Zotero.Server.Endpoints[CONTEXT_ROUTE] = contextEndpointClass();
  Zotero.Server.Endpoints[RENDER_ROUTE] = renderEndpointClass();
  Zotero.Server.Endpoints[NAVIGATE_ROUTE] = navigateEndpointClass();
  Zotero.Server.Endpoints[ITEM_MERGE_ROUTE] = itemMergeEndpointClass();
  Zotero.debug(`Zotero Modified Bridge ${bridgeVersion} started`);
}

function shutdown() {
  for (let route of ROUTES) delete Zotero.Server.Endpoints[route];
  bridgeVersion = "unknown";
}

function install() {}
function uninstall() {}
