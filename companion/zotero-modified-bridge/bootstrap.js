const STATUS_ROUTE = "/api/users/:userID/zotero-modified/statuses";
const STYLES_ROUTE = "/api/users/:userID/zotero-modified/styles";
const CONTEXT_ROUTE = "/api/users/:userID/zotero-modified/context";
const RENDER_ROUTE = "/api/users/:userID/zotero-modified/render";
const NAVIGATE_ROUTE = "/api/users/:userID/zotero-modified/navigate";
const TAG_RENAME_ROUTE = "/api/users/:userID/zotero-modified/tags/rename";
const TAG_MERGE_ROUTE = "/api/users/:userID/zotero-modified/tags/merge";
const ROUTES = [
  STATUS_ROUTE,
  STYLES_ROUTE,
  CONTEXT_ROUTE,
  RENDER_ROUTE,
  NAVIGATE_ROUTE,
  TAG_RENAME_ROUTE,
  TAG_MERGE_ROUTE,
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

function normalizedTagName(value) {
  return typeof value === "string" ? value.trim().normalize() : "";
}

function tagColor(libraryID, name) {
  const value = Zotero.Tags.getColors(libraryID).get(name);
  return value ? { color: value.color, position: value.position } : null;
}

async function tagImpact(libraryID, name) {
  const tagID = Zotero.Tags.getID(name);
  const color = tagColor(libraryID, name);
  const itemIDs = tagID ? await Zotero.Tags.getTagItems(libraryID, tagID) : [];
  return {
    tagID: tagID || null,
    itemIDs,
    color,
    exists: itemIDs.length > 0 || !!color,
  };
}

function editableLibrary(libraryID) {
  const library = Zotero.Libraries.get(libraryID);
  return library && library.editable !== false;
}

function expectedCount(value) {
  return Number.isInteger(value) && value >= 0 ? value : null;
}

function tagCountMismatch(name, expected, actual) {
  return errorResponse(
    412,
    "tag-impact-changed",
    `Tag '${name}' affects ${actual} items, expected ${expected}.`,
    true,
    { name, expectedCount: expected, actualCount: actual }
  );
}

function restoreTagColor(libraryID, name, color) {
  if (!color) return Zotero.Tags.setColor(libraryID, name, false);
  return Zotero.Tags.setColor(libraryID, name, color.color, color.position);
}

function tagRenameEndpointClass() {
  return class ModifiedTagRename extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["POST"];

    async run(requestData) {
      try {
        const body = parseBody(this, requestData);
        const from = normalizedTagName(body.from);
        const to = normalizedTagName(body.to);
        const count = expectedCount(body.expectedCount);
        if (!from || !to || from === to) {
          return errorResponse(400, "invalid-tag-names", "from and to must be distinct non-empty tag names");
        }
        if (count === null) {
          return errorResponse(400, "invalid-expected-count", "expectedCount must be a non-negative integer");
        }
        if (!editableLibrary(requestData.libraryID)) {
          return errorResponse(423, "library-read-only", "The Zotero library is not editable.");
        }

        const impact = await tagImpact(requestData.libraryID, from);
        if (!impact.tagID || !impact.exists) {
          return errorResponse(404, "tag-not-found", `Tag '${from}' was not found in this library.`);
        }
        if (impact.itemIDs.length !== count) return tagCountMismatch(from, count, impact.itemIDs.length);

        const targetImpact = await tagImpact(requestData.libraryID, to);
        const targetExists = targetImpact.exists;
        const targetColor = targetImpact.color;
        await Zotero.Tags.rename(requestData.libraryID, from, to);
        if (targetExists) await restoreTagColor(requestData.libraryID, to, targetColor);
        return jsonResponse(200, {
          renamed: true,
          from,
          to,
          affectedItems: impact.itemIDs.length,
          targetExisted: targetExists,
        });
      }
      catch (error) {
        return internalError(error, "Zotero could not rename the tag.");
      }
    }
  };
}

function tagMergeEndpointClass() {
  return class ModifiedTagMerge extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["POST"];

    async run(requestData) {
      try {
        const body = parseBody(this, requestData);
        const into = normalizedTagName(body.into);
        const colorPolicy = body.colorPolicy === undefined ? "preserve-target" : body.colorPolicy;
        if (!into || !Array.isArray(body.sources) || body.sources.length < 1 || body.sources.length > 50) {
          return errorResponse(400, "invalid-tag-merge", "into and 1–50 sources are required");
        }
        if (colorPolicy !== "preserve-target") {
          return errorResponse(400, "invalid-color-policy", "Only preserve-target is supported");
        }

        const sources = [];
        const seen = new Set([into]);
        for (const entry of body.sources) {
          if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
            return errorResponse(400, "invalid-tag-source", "Each source must contain name and expectedCount");
          }
          const name = normalizedTagName(entry.name);
          const count = expectedCount(entry.expectedCount);
          if (!name || seen.has(name) || count === null) {
            return errorResponse(400, "invalid-tag-source", "Sources must have unique names and non-negative expectedCount values");
          }
          seen.add(name);
          sources.push({ name, expectedCount: count });
        }
        if (!editableLibrary(requestData.libraryID)) {
          return errorResponse(423, "library-read-only", "The Zotero library is not editable.");
        }

        const targetImpact = await tagImpact(requestData.libraryID, into);
        const targetExists = targetImpact.exists;
        const targetColor = targetImpact.color;
        const impacts = [];
        const affectedItems = new Set();
        let fallbackColor = null;
        for (const source of sources) {
          const impact = await tagImpact(requestData.libraryID, source.name);
          if (!impact.tagID || !impact.exists) {
            return errorResponse(404, "tag-not-found", `Tag '${source.name}' was not found in this library.`);
          }
          if (impact.itemIDs.length !== source.expectedCount) {
            return tagCountMismatch(source.name, source.expectedCount, impact.itemIDs.length);
          }
          const color = tagColor(requestData.libraryID, source.name);
          if (!fallbackColor && color) fallbackColor = color;
          for (const itemID of impact.itemIDs) affectedItems.add(itemID);
          impacts.push({ ...source, itemIDs: impact.itemIDs, color });
        }

        for (const source of impacts) {
          await Zotero.Tags.rename(requestData.libraryID, source.name, into);
          await restoreTagColor(
            requestData.libraryID,
            into,
            targetExists ? targetColor : fallbackColor
          );
        }
        return jsonResponse(200, {
          merged: true,
          from: sources.map((source) => source.name),
          into,
          affectedItems: affectedItems.size,
          targetExisted: targetExists,
          colorPolicy,
        });
      }
      catch (error) {
        return internalError(error, "Zotero could not merge the tags.");
      }
    }
  };
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

async function startup(data) {
  bridgeVersion = data && data.version ? String(data.version) : "unknown";
  await Zotero.initializationPromise;
  Zotero.Server.Endpoints[STATUS_ROUTE] = statusEndpointClass();
  Zotero.Server.Endpoints[STYLES_ROUTE] = stylesEndpointClass();
  Zotero.Server.Endpoints[CONTEXT_ROUTE] = contextEndpointClass();
  Zotero.Server.Endpoints[RENDER_ROUTE] = renderEndpointClass();
  Zotero.Server.Endpoints[NAVIGATE_ROUTE] = navigateEndpointClass();
  Zotero.Server.Endpoints[TAG_RENAME_ROUTE] = tagRenameEndpointClass();
  Zotero.Server.Endpoints[TAG_MERGE_ROUTE] = tagMergeEndpointClass();
  Zotero.debug(`Zotero Modified Bridge ${bridgeVersion} started`);
}

function shutdown() {
  for (let route of ROUTES) delete Zotero.Server.Endpoints[route];
  bridgeVersion = "unknown";
}

function install() {}
function uninstall() {}
