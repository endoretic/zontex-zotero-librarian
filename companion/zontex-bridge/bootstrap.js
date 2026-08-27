const STATUS_ROUTE = "/api/users/:userID/zontex/statuses";
const STYLES_ROUTE = "/api/users/:userID/zontex/styles";
const CONTEXT_ROUTE = "/api/users/:userID/zontex/context";
const RENDER_ROUTE = "/api/users/:userID/zontex/render";
const NAVIGATE_ROUTE = "/api/users/:userID/zontex/navigate";
const ITEM_MERGE_ROUTE = "/api/users/:userID/zontex/items/merge";
const DOCUMENT_SEGMENTS_ROUTE = "/api/users/:userID/zontex/document-segments";
const ANNOTATIONS_ROUTE = "/api/users/:userID/zontex/annotations";
const ANNOTATION_NOTE_ROUTE = "/api/users/:userID/zontex/annotations/note";
const TESTED_ZOTERO_VERSION = "10.0.1";
const PRIVATE_ANNOTATION_BACKEND = "private-reader-internals";
const TAG_RENAME_ROUTE = "/api/users/:userID/zontex/tags/rename";
const TAG_MERGE_ROUTE = "/api/users/:userID/zontex/tags/merge";
const ROUTES = [
  STATUS_ROUTE,
  STYLES_ROUTE,
  CONTEXT_ROUTE,
  RENDER_ROUTE,
  NAVIGATE_ROUTE,
  DOCUMENT_SEGMENTS_ROUTE,
  ANNOTATIONS_ROUTE,
  ANNOTATION_NOTE_ROUTE,
  TAG_RENAME_ROUTE,
  TAG_MERGE_ROUTE,
  ITEM_MERGE_ROUTE,
];
let bridgeVersion = "unknown";
const reportedCompatibilityWarnings = new Set();

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
    if (!entry || entry.length > itemMax) return null;
    if (result.includes(entry)) continue;
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

function privateAnnotationSurface(reader) {
  const internalReader = reader?._internalReader;
  if (!internalReader) return { state: reader ? "initializing" : "inactive", compatible: false, missing: [] };
  const missing = [];
  if (!reader?._iframeWindow || typeof reader._iframeWindow !== "object") missing.push("reader._iframeWindow");
  if (typeof internalReader._loadSDT !== "function") missing.push("reader._internalReader._loadSDT");
  if (typeof internalReader._getSourceAnnotationMeta !== "function") {
    missing.push("reader._internalReader._getSourceAnnotationMeta");
  }
  if (typeof internalReader._annotationManager?.addAnnotation !== "function") {
    missing.push("reader._internalReader._annotationManager.addAnnotation");
  }
  if (typeof Components === "undefined" || typeof Components.utils?.cloneInto !== "function") {
    missing.push("Components.utils.cloneInto");
  }
  return {
    state: missing.length ? "incompatible" : "available",
    compatible: missing.length === 0,
    missing,
  };
}

function annotationCompatibility(reader = null) {
  const privateAPI = privateAnnotationSurface(reader);
  let standardAvailable = false;
  try {
    standardAvailable = typeof reader?.createAnnotationFromSDT === "function"
      || typeof reader?._internalReader?._primaryView?.createAnnotationFromSDT === "function";
  }
  catch (_) {}
  const zoteroVersion = typeof Zotero.version === "string" ? Zotero.version : null;
  const warnings = [];
  if (zoteroVersion && zoteroVersion !== TESTED_ZOTERO_VERSION) {
    warnings.push(
      `Active annotation was tested with Zotero ${TESTED_ZOTERO_VERSION}; review private Reader compatibility for ${zoteroVersion}.`
    );
  }
  if (standardAvailable) {
    warnings.push(
      "Zotero now exposes createAnnotationFromSDT; update the Bridge to use it as primary and keep the private backend as fallback."
    );
  }
  if (privateAPI.state === "incompatible") {
    warnings.push(`The experimental private annotation backend changed or failed: ${privateAPI.missing.join(", ")}.`);
  }
  return {
    experimental: true,
    backend: privateAPI.compatible ? PRIVATE_ANNOTATION_BACKEND : null,
    testedZoteroVersion: TESTED_ZOTERO_VERSION,
    zoteroVersion,
    standardAvailable,
    privateAPI,
    warnings,
  };
}

function reportCompatibilityWarnings(compatibility) {
  for (let warning of compatibility.warnings) {
    if (reportedCompatibilityWarnings.has(warning)) continue;
    reportedCompatibilityWarnings.add(warning);
    Zotero.logError(new Error(`[Zontex Bridge] ${warning}`));
  }
}

function readerCapabilities(reader, type) {
  const annotation = annotationCompatibility(reader);
  reportCompatibilityWarnings(annotation);
  const pdfAnnotations = type === "pdf" && annotation.privateAPI.compatible;
  return {
    sdt: typeof Zotero.SDT?.getReader === "function",
    createAnnotationFromSDT: annotation.privateAPI.compatible,
    highlight: pdfAnnotations,
    underline: pdfAnnotations,
    annotation,
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
    capabilities: readerCapabilities(reader, type),
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

function internalError(error, message = "Unexpected Zontex Bridge error") {
  if (Number.isInteger(error?.bridgeStatus)) {
    return errorResponse(
      error.bridgeStatus,
      error.bridgeCode || "invalid-request",
      error.message || "The request is invalid.",
      false,
      error.bridgeDetails
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
  return class ZontexTagRename extends Zotero.Server.LocalAPI.Settings {
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
  return class ZontexTagMerge extends Zotero.Server.LocalAPI.Settings {
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
  return class ZontexStatuses extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["GET", "PUT", "DELETE"];

    async run(requestData) {
      try {
      let { libraryID, method, searchParams } = requestData;
      if (method === "GET") {
        let all = coloredTags(libraryID);
        const compatibility = annotationCompatibility(getActiveReader());
        reportCompatibilityWarnings(compatibility);
        return jsonResponse(200, {
          bridge: "zontex-bridge",
          version: bridgeVersion,
          compatibility,
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
  return class ZontexStyles extends Zotero.Server.LocalAPI.Settings {
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
  return class ZontexContext extends Zotero.Server.LocalAPI.Settings {
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
          bridge: "zontex-bridge",
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
  return class ZontexRender extends Zotero.Server.LocalAPI.Settings {
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
  return class ZontexNavigate extends Zotero.Server.LocalAPI.Settings {
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

function sdtChildren(node) {
  if (Array.isArray(node)) return node;
  for (let name of ["children", "content", "nodes", "blocks"]) {
    if (Array.isArray(node?.[name])) return node[name];
  }
  return [];
}

function sdtText(node) {
  if (typeof node === "string") return node;
  if (typeof node?.text === "string" && !sdtChildren(node).length) return node.text;
  if (typeof node?.value === "string" && !sdtChildren(node).length) return node.value;
  return sdtChildren(node).map(sdtText).join("");
}

function collectSDTSpans(node, ref, spans) {
  const children = sdtChildren(node);
  const text = typeof node === "string"
    ? node
    : (!children.length && typeof node?.text === "string" ? node.text :
      (!children.length && typeof node?.value === "string" ? node.value : null));
  if (text === null) {
    children.forEach((child, index) => collectSDTSpans(child, [...ref, index], spans));
    return;
  }
  if (!text) return;
  const textStart = spans.length ? spans[spans.length - 1].textEnd : 0;
  spans.push({
    textStart,
    textEnd: textStart + text.length,
    ref: ref.length ? ref : [0],
    sourceStart: 0,
    sourceEnd: text.length,
  });
}

function isSDTLeafBlock(node) {
  if (!node || typeof node.text === "string") return false;
  if (!Array.isArray(node.content) || !node.content.length) return true;
  return !node.content.some((child) => child && typeof child.text !== "string");
}

function materializedSDTSegments(document, includeAuxiliary = false) {
  const content = Array.isArray(document?.content)
    ? document.content
    : (Array.isArray(document?.content?.blocks) ? document.content.blocks : []);
  const segments = [];

  function visit(node, ref, flowClass) {
    if (!node || typeof node.text === "string") return;
    if (isSDTLeafBlock(node)) {
      const spans = [];
      collectSDTSpans(node, ref, spans);
      const text = sdtText(node);
      if (text && spans.length) {
        segments.push({
          id: `block:${ref.join(".")}`,
          blockType: node.blockType || node.type || "block",
          flowClass: node.flowClass || flowClass || null,
          text,
          locator: { kind: "sdt-block", blockRef: ref },
          spans,
        });
      }
      return;
    }
    node.content.forEach((child, index) => {
      if (child && typeof child.text !== "string") visit(child, [...ref, index], flowClass);
    });
  }

  content.forEach((block, index) => {
    const auxiliary = block?.auxiliary || block?.isAuxiliary || block?.flowClass === "excluded";
    if (!includeAuxiliary && auxiliary) return;
    visit(block, [index], block?.flowClass || null);
  });
  return segments;
}

// SDT is a binary pack in Zotero. Keep decoding behind feature detection so a
// Zotero build without the bundled SDT reader returns a capability error.
async function loadSDTDocument(attachment) {
  if (typeof Zotero.SDT?.getReader !== "function") return null;
  const reader = await Zotero.SDT.getReader(attachment.id, { isPriority: true });
  if (!reader) return null;
  if (typeof reader.materialize === "function") return await reader.materialize();
  return reader.document || reader;
}

async function activePDFAttachment(libraryID, attachmentKey) {
  const reader = getActiveReader();
  if (!reader) return { response: errorResponse(409, "reader-required", "An active Reader is required.", true) };
  await waitForReaderView(reader);
  const attachment = Zotero.Items.get(reader.itemID) || await Zotero.Items.getAsync(reader.itemID);
  if (!attachment || attachment.libraryID !== libraryID || (attachmentKey && attachment.key !== attachmentKey)) {
    return { response: errorResponse(409, "reader-mismatch", "The active Reader does not match the requested attachment.", true) };
  }
  if (reader.type !== "pdf") {
    return { response: errorResponse(422, "unsupported-reader", "Annotation V1 requires an active PDF Reader.") };
  }
  return {
    reader,
    internalReader: reader?._internalReader,
    attachment,
    view: reader?._internalReader?._primaryView,
  };
}

function documentSourceHash(document) {
  return document?.metadata?.source?.hash || document?.metadata?.sourceHash || null;
}

function documentSegmentsEndpointClass() {
  return class ZontexDocumentSegments extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["GET"];

    async run(requestData) {
      try {
        const query = requestData.searchParams;
        const limit = Number(query.get("limit") || 100);
        const cursor = Number(query.get("cursor") || 0);
        const includeAuxiliary = query.get("includeAuxiliary") === "1";
        if (!Number.isInteger(limit) || limit < 1 || limit > 500
          || !Number.isInteger(cursor) || cursor < 0) {
          return errorResponse(400, "invalid-pagination", "limit must be 1–500 and cursor must be a non-negative integer");
        }

        const active = await activePDFAttachment(requestData.libraryID, query.get("attachmentKey"));
        if (active.response) return active.response;
        const document = await loadSDTDocument(active.attachment);
        if (!document) {
          return errorResponse(501, "sdt-unavailable", "Structured Document Text is unavailable in this Zotero build.", true);
        }
        const allSegments = materializedSDTSegments(document, includeAuxiliary);
        const segments = allSegments.slice(cursor, cursor + limit);
        const next = cursor + segments.length < allSegments.length ? String(cursor + segments.length) : null;
        return jsonResponse(200, {
          attachment: { key: active.attachment.key, libraryID: active.attachment.libraryID },
          document: {
            sourceHash: documentSourceHash(document),
            schemaVersion: document.schemaVersion || null,
            processorType: document.metadata?.processor?.type || active.reader.type,
          },
          segments,
          nextCursor: next,
        });
      }
      catch (error) {
        return internalError(error, "Zotero could not read the document segments.");
      }
    }
  };
}

function annotationRecord(annotation, attachmentKey) {
  let json;
  try {
    json = Zotero.Annotations.toJSONSync(annotation);
  }
  catch (_) {
    json = {};
  }
  return {
    key: json.key || annotation.key,
    attachmentKey,
    type: json.type || annotation.annotationType,
    text: json.text || annotation.annotationText || "",
    comment: json.comment || annotation.annotationComment || "",
    color: json.color || annotation.annotationColor || null,
    pageLabel: json.pageLabel || annotation.annotationPageLabel || null,
    sortIndex: json.sortIndex || annotation.annotationSortIndex || null,
    position: json.position || null,
  };
}

function annotationJSON(annotation) {
  try {
    return Zotero.Annotations.toJSONSync(annotation);
  }
  catch (_) {
    return {
      key: annotation.key,
      type: annotation.annotationType,
      text: annotation.annotationText || "",
      position: annotation.annotationPosition ? JSON.parse(annotation.annotationPosition) : null,
    };
  }
}

function sameAnnotationPosition(annotation, expectedPosition) {
  if (!expectedPosition || annotation.deleted) return false;
  const position = annotationJSON(annotation).position;
  function canonical(value) {
    if (typeof value === "number") return Math.round(value * 1000) / 1000;
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === "object") {
      return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
    }
    return value;
  }
  return !!position && JSON.stringify(canonical(position)) === JSON.stringify(canonical(expectedPosition));
}

function sdtAnchorForRange(segment, start, end) {
  function refFor(offset, ending) {
    for (let span of segment.spans) {
      if (offset < span.textEnd || (ending && offset === span.textEnd)) {
        return [...span.ref, span.sourceStart + offset - span.textStart];
      }
    }
    const last = segment.spans[segment.spans.length - 1];
    return [...last.ref, last.sourceEnd];
  }
  return { start: refFor(start, false), end: refFor(end, true) };
}

function privateAnnotationFailure(message, missing = []) {
  const warning = `The experimental private annotation backend changed or failed: ${missing.join(", ") || message}.`;
  reportCompatibilityWarnings({ warnings: [warning] });
  const error = new Error(message);
  error.bridgeStatus = 501;
  error.bridgeCode = "annotation-backend-incompatible";
  error.bridgeDetails = {
    backend: PRIVATE_ANNOTATION_BACKEND,
    experimental: true,
    missing,
  };
  return error;
}

function unwrapReaderValue(value) {
  if (!value || typeof value !== "object") return value;
  if (value.wrappedJSObject) return value.wrappedJSObject;
  if (typeof Components.utils?.waiveXrays === "function") {
    return Components.utils.waiveXrays(value);
  }
  return value;
}

async function buildPrivateSDTAnnotation(active, sdtAnchor, type, text) {
  const compatibility = annotationCompatibility(active.reader);
  if (!compatibility.privateAPI.compatible) {
    throw privateAnnotationFailure(
      "The experimental native annotation backend is incompatible with this Zotero build.",
      compatibility.privateAPI.missing
    );
  }

  const internalReader = active.internalReader;
  const sdt = unwrapReaderValue(await internalReader._loadSDT());
  if (!sdt) {
    const error = new Error("Structured Document Text is unavailable in the active Reader.");
    error.bridgeStatus = 501;
    error.bridgeCode = "sdt-unavailable";
    throw error;
  }
  const mapper = unwrapReaderValue(sdt.mapper);
  const missing = [];
  if (typeof mapper?.sdtToSourcePosition !== "function") missing.push("sdt.mapper.sdtToSourcePosition");
  if (typeof mapper?.transformAnnotationPosition !== "function") {
    missing.push("sdt.mapper.transformAnnotationPosition");
  }
  if (missing.length) {
    throw privateAnnotationFailure(
      "Zotero's private SDT position mapper no longer matches the tested implementation.",
      missing
    );
  }

  const clonedAnchor = Components.utils.cloneInto(sdtAnchor, active.reader._iframeWindow);
  let position = mapper.sdtToSourcePosition(clonedAnchor);
  if (!position) {
    const error = new Error("The SDT target could not be mapped to a native PDF position.");
    error.bridgeStatus = 422;
    error.bridgeCode = "annotation-position-unavailable";
    throw error;
  }
  position = mapper.transformAnnotationPosition(position, type);
  const meta = internalReader._getSourceAnnotationMeta(position);
  if (!meta?.sortIndex) {
    const error = new Error("The active PDF view could not resolve annotation page metadata.");
    error.bridgeStatus = 422;
    error.bridgeCode = "annotation-metadata-unavailable";
    throw error;
  }
  return {
    position,
    text,
    sortIndex: meta.sortIndex,
    pageLabel: meta.pageLabel || "",
  };
}

function createPrivateSDTAnnotation(active, built, { type, color, comment, tags }) {
  // ponytail: Keep this adapter as the primary path until Zotero exposes the
  // desktop API; the compatibility probe tells us when to invert it to fallback.
  const payload = Components.utils.cloneInto({
    type,
    color,
    comment,
    tags,
    position: built.position,
    text: built.text,
    sortIndex: built.sortIndex,
    pageLabel: built.pageLabel,
  }, active.reader._iframeWindow);
  return active.internalReader._annotationManager.addAnnotation(payload);
}

async function waitForAnnotationItem(attachment, key) {
  for (let attempt = 0; attempt < 60; attempt++) {
    const annotation = attachment.getAnnotations().find((item) => item.key === key);
    try {
      if (annotation?.annotationType && annotation.annotationPosition) return annotation;
    }
    catch (_) {}
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return null;
}

function annotationsEndpointClass() {
  return class ZontexAnnotations extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["POST"];

    async run(requestData) {
      try {
        const body = parseBody(this, requestData);
        const attachmentKey = body.attachmentKey;
        if (typeof attachmentKey !== "string" || !attachmentKey.trim()) {
          return errorResponse(400, "invalid-attachment-key", "attachmentKey is required");
        }
        const type = body.type;
        if (!["highlight", "underline"].includes(type)) {
          return errorResponse(400, "invalid-annotation-type", "type must be highlight or underline");
        }
        const color = body.color || "#ffd400";
        if (!validateHexColor(color)) return errorResponse(400, "invalid-color", "color must use #RRGGBB syntax");
        const comment = body.comment === undefined ? "" : body.comment;
        if (typeof comment !== "string" || comment.length > 4000) {
          return errorResponse(400, "invalid-comment", "comment must be at most 4000 characters");
        }
        const tags = body.tags === undefined ? [] : normalizeStringArray(body.tags);
        if (!tags) return errorResponse(400, "invalid-tags", "tags must contain at most 20 unique strings of 100 characters");

        const active = await activePDFAttachment(requestData.libraryID, attachmentKey.trim());
        if (active.response) return active.response;
        if (typeof active.attachment.isEditable !== "function"
          || !active.attachment.isEditable() || active.attachment.deleted) {
          return errorResponse(423, "library-read-only", "The active attachment or library is read-only.", true);
        }

        const target = body.target;
        if (!target || typeof target.segmentId !== "string"
          || !Number.isInteger(target.start) || !Number.isInteger(target.end)
          || target.start < 0 || target.end <= target.start) {
          return errorResponse(400, "invalid-target", "target must contain segmentId and a non-empty [start,end) range");
        }
        const document = await loadSDTDocument(active.attachment);
        if (!document) return errorResponse(501, "sdt-unavailable", "Structured Document Text is unavailable in this Zotero build.", true);
        if (typeof body.sourceHash !== "string" || !body.sourceHash
          || body.sourceHash !== documentSourceHash(document)) {
          return errorResponse(412, "document-changed", "The document changed; refetch segments and relocate the target.", true);
        }
        const segment = materializedSDTSegments(document).find((entry) => entry.id === target.segmentId);
        if (!segment) return errorResponse(404, "segment-not-found", "The requested document segment was not found.");
        if (target.end > segment.text.length) return errorResponse(400, "invalid-target", "target end exceeds segment text length");
        const text = segment.text.slice(target.start, target.end);
        const sdtAnchor = sdtAnchorForRange(segment, target.start, target.end);

        const built = await buildPrivateSDTAnnotation(active, sdtAnchor, type, text);
        const expectedPosition = built.position;
        const duplicate = text
          ? active.attachment.getAnnotations().find((annotation) => {
            if (!sameAnnotationPosition(annotation, expectedPosition)) return false;
            if (annotation.annotationType !== type) return false;
            const json = annotationJSON(annotation);
            return (json.text || "").normalize() === text.normalize()
              && (json.comment || "") === comment
              && (!color || json.color === color);
          }) || null
          : null;
        if (duplicate) {
          return jsonResponse(200, {
            created: false,
            duplicate: true,
            annotation: annotationRecord(duplicate, active.attachment.key),
          });
        }

        const created = createPrivateSDTAnnotation(active, built, { type, color, comment, tags });
        const createdKey = created?.id || created?.key || null;
        const annotation = await waitForAnnotationItem(active.attachment, createdKey)
          || (text ? active.attachment.getAnnotations().find((item) => (
            sameAnnotationPosition(item, expectedPosition)
            && item.annotationType === type
          )) : null);
        if (!annotation) {
          return errorResponse(500, "annotation-readback-failed", "Zotero did not expose the created annotation after the native write.", true);
        }
        return jsonResponse(200, {
          created: true,
          annotation: annotationRecord(annotation, active.attachment.key),
        });
      }
      catch (error) {
        return internalError(error, "Zotero could not create the native annotation.");
      }
    }
  };
}

function annotationNoteEndpointClass() {
  return class ZontexAnnotationNote extends Zotero.Server.LocalAPI.Settings {
    supportedMethods = ["POST"];

    async run(requestData) {
      try {
        const body = parseBody(this, requestData);
        const annotationKeys = Array.isArray(body.annotationKeys)
          ? body.annotationKeys.map((key) => typeof key === "string" ? key.trim() : "")
          : null;
        if (!annotationKeys || annotationKeys.length < 1 || annotationKeys.length > 50
          || annotationKeys.some((key) => !key) || new Set(annotationKeys).size !== annotationKeys.length) {
          return errorResponse(400, "invalid-annotation-keys", "annotationKeys must contain 1–50 annotation keys");
        }
        if (typeof body.parentItemKey !== "string" || !body.parentItemKey.trim()) {
          return errorResponse(400, "invalid-parent-item-key", "parentItemKey is required");
        }
        const order = body.order || "document";
        if (!["document", "provided"].includes(order)) {
          return errorResponse(400, "invalid-order", "order must be document or provided");
        }
        const parent = await itemByKey(requestData.libraryID, body.parentItemKey);
        if (!parent) return errorResponse(404, "item-not-found", "The requested parent item was not found.");
        if (!parent.isRegularItem?.() || !parent.isTopLevelItem?.()) {
          return errorResponse(422, "invalid-parent-item", "parentItemKey must identify a top-level regular item.");
        }
        if (parent.deleted || (typeof parent.isEditable === "function" && !parent.isEditable())) {
          return errorResponse(423, "library-read-only", "The parent item or library is read-only.", true);
        }
        const annotations = [];
        for (let key of annotationKeys) {
          const annotation = await itemByKey(requestData.libraryID, key);
          if (!annotation) return errorResponse(404, "annotation-not-found", `Annotation '${key}' was not found.`);
          if (!annotation.isAnnotation?.()) return errorResponse(422, "invalid-annotation", `Item '${key}' is not an annotation.`);
          const annotationParentID = annotation.parentItemID || annotation.parentID;
          const attachment = annotationParentID
            ? (Zotero.Items.get(annotationParentID) || await Zotero.Items.getAsync(annotationParentID))
            : null;
          if (!attachment?.isAttachment?.() || attachment.parentItemID !== parent.id) {
            return errorResponse(422, "mixed-parent-annotations", "All annotations must belong to the requested parent item.");
          }
          annotations.push(annotation);
        }
        if (order === "document") {
          annotations.sort((a, b) => String(a.annotationSortIndex || "").localeCompare(String(b.annotationSortIndex || "")));
        }
        if (typeof Zotero.EditorInstance?.createNoteFromAnnotations !== "function") {
          return errorResponse(501, "annotation-note-unavailable", "Native annotation-note creation is unavailable.", true);
        }
        const note = await Zotero.EditorInstance.createNoteFromAnnotations(annotations, {
          parentID: parent.id,
          noComments: !!body.noComments,
          noHeader: !!body.noHeader,
        });
        return jsonResponse(200, {
          created: true,
          note: { key: note.key, parentItemKey: parent.key },
          annotationKeys: annotations.map((annotation) => annotation.key),
        });
      }
      catch (error) {
        return internalError(error, "Zotero could not create the annotation note.");
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
  return class ZontexItemMerge extends Zotero.Server.LocalAPI.Settings {
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
  reportCompatibilityWarnings(annotationCompatibility());
  Zotero.Server.Endpoints[STATUS_ROUTE] = statusEndpointClass();
  Zotero.Server.Endpoints[STYLES_ROUTE] = stylesEndpointClass();
  Zotero.Server.Endpoints[CONTEXT_ROUTE] = contextEndpointClass();
  Zotero.Server.Endpoints[RENDER_ROUTE] = renderEndpointClass();
  Zotero.Server.Endpoints[NAVIGATE_ROUTE] = navigateEndpointClass();
  Zotero.Server.Endpoints[DOCUMENT_SEGMENTS_ROUTE] = documentSegmentsEndpointClass();
  Zotero.Server.Endpoints[ANNOTATIONS_ROUTE] = annotationsEndpointClass();
  Zotero.Server.Endpoints[ANNOTATION_NOTE_ROUTE] = annotationNoteEndpointClass();
  Zotero.Server.Endpoints[TAG_RENAME_ROUTE] = tagRenameEndpointClass();
  Zotero.Server.Endpoints[TAG_MERGE_ROUTE] = tagMergeEndpointClass();
  Zotero.Server.Endpoints[ITEM_MERGE_ROUTE] = itemMergeEndpointClass();
  Zotero.debug(`Zontex Bridge ${bridgeVersion} started`);
}

function shutdown() {
  for (let route of ROUTES) delete Zotero.Server.Endpoints[route];
  reportedCompatibilityWarnings.clear();
  bridgeVersion = "unknown";
}

function install() {}
function uninstall() {}
