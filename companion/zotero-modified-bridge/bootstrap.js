const STATUS_ROUTE = "/api/users/:userID/zotero-modified/statuses";
const STYLES_ROUTE = "/api/users/:userID/zotero-modified/styles";
const CONTEXT_ROUTE = "/api/users/:userID/zotero-modified/context";
const RENDER_ROUTE = "/api/users/:userID/zotero-modified/render";
const NAVIGATE_ROUTE = "/api/users/:userID/zotero-modified/navigate";
const DOCUMENT_SEGMENTS_ROUTE = "/api/users/:userID/zotero-modified/document-segments";
const ANNOTATIONS_ROUTE = "/api/users/:userID/zotero-modified/annotations";
const ANNOTATION_NOTE_ROUTE = "/api/users/:userID/zotero-modified/annotations/note";
const ROUTES = [
  STATUS_ROUTE,
  STYLES_ROUTE,
  CONTEXT_ROUTE,
  RENDER_ROUTE,
  NAVIGATE_ROUTE,
  DOCUMENT_SEGMENTS_ROUTE,
  ANNOTATIONS_ROUTE,
  ANNOTATION_NOTE_ROUTE,
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
  return { reader, attachment, view: reader?._internalReader?._primaryView };
}

function documentSourceHash(document) {
  return document?.metadata?.source?.hash || document?.metadata?.sourceHash || null;
}

function documentSegmentsEndpointClass() {
  return class ModifiedDocumentSegments extends Zotero.Server.LocalAPI.Settings {
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
  if (!expectedPosition) return false;
  const position = annotationJSON(annotation).position;
  return !!position && JSON.stringify(position) === JSON.stringify(expectedPosition);
}

function validSDTRefPath(value) {
  return Array.isArray(value) && value.length > 0
    && value.every((entry) => Number.isInteger(entry) && entry >= 0);
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

function annotationsEndpointClass() {
  return class ModifiedAnnotations extends Zotero.Server.LocalAPI.Settings {
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
        if (typeof active.view?.createAnnotationFromSDT !== "function") {
          return errorResponse(501, "annotation-unavailable", "Native SDT annotation creation is unavailable in this Zotero build.", true);
        }
        if (typeof active.attachment.isEditable !== "function"
          || !active.attachment.isEditable() || active.attachment.deleted) {
          return errorResponse(423, "library-read-only", "The active attachment or library is read-only.", true);
        }

        let sdtAnchor;
        let text = "";
        if (body.target?.kind === "sdt") {
          if (!validSDTRefPath(body.target.start) || !validSDTRefPath(body.target.end)) {
            return errorResponse(400, "invalid-sdt-target", "raw SDT targets require start and end RefPaths");
          }
          sdtAnchor = { start: body.target.start, end: body.target.end };
        }
        else {
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
          text = segment.text.slice(target.start, target.end);
          sdtAnchor = sdtAnchorForRange(segment, target.start, target.end);
        }

        let expectedPosition = null;
        if (text && typeof active.view?.sdtAnchorToPosition === "function") {
          expectedPosition = await active.view.sdtAnchorToPosition(sdtAnchor);
        }
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

        const payload = { sdtAnchor, type, color, comment, tags };
        const iframeWindow = active.view?._iframeWindow;
        if (!iframeWindow || typeof Components === "undefined"
          || typeof Components.utils?.cloneInto !== "function") {
          return errorResponse(501, "reader-bridge-unavailable", "The active Reader iframe is unavailable.", true);
        }
        const created = await active.view.createAnnotationFromSDT(
          Components.utils.cloneInto(payload, iframeWindow)
        );
        const createdKey = created?.id || created?.key || null;
        const annotation = active.attachment.getAnnotations().find((item) => item.key === createdKey)
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
  return class ModifiedAnnotationNote extends Zotero.Server.LocalAPI.Settings {
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

async function startup(data) {
  bridgeVersion = data && data.version ? String(data.version) : "unknown";
  await Zotero.initializationPromise;
  Zotero.Server.Endpoints[STATUS_ROUTE] = statusEndpointClass();
  Zotero.Server.Endpoints[STYLES_ROUTE] = stylesEndpointClass();
  Zotero.Server.Endpoints[CONTEXT_ROUTE] = contextEndpointClass();
  Zotero.Server.Endpoints[RENDER_ROUTE] = renderEndpointClass();
  Zotero.Server.Endpoints[NAVIGATE_ROUTE] = navigateEndpointClass();
  Zotero.Server.Endpoints[DOCUMENT_SEGMENTS_ROUTE] = documentSegmentsEndpointClass();
  Zotero.Server.Endpoints[ANNOTATIONS_ROUTE] = annotationsEndpointClass();
  Zotero.Server.Endpoints[ANNOTATION_NOTE_ROUTE] = annotationNoteEndpointClass();
  Zotero.debug(`Zotero Modified Bridge ${bridgeVersion} started`);
}

function shutdown() {
  for (let route of ROUTES) delete Zotero.Server.Endpoints[route];
  bridgeVersion = "unknown";
}

function install() {}
function uninstall() {}
