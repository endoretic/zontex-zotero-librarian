const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const bridgePath = path.join(__dirname, "..", "companion", "zotero-modified-bridge", "bootstrap.js");

function makeItem(key, overrides = {}) {
  return {
    id: overrides.id || key.charCodeAt(0),
    key,
    itemType: overrides.itemType || "journalArticle",
    version: overrides.version ?? 1,
    deleted: false,
    parentItemID: null,
    attachmentReaderType: null,
    getField(field) {
      return field === "title" ? (overrides.title || key) : null;
    },
    isAttachment: () => false,
    isAnnotation: () => false,
    isEditable: () => true,
    isNote: () => false,
    isRegularItem: () => true,
    isTopLevelItem: () => true,
    ...overrides,
  };
}

function loadBridge(overrides = {}) {
  const items = overrides.items || new Map();
  const endpoints = {};
  const zotero = {
    initializationPromise: Promise.resolve(),
    Server: { Endpoints: endpoints, LocalAPI: { Settings: class {} } },
    Items: {
      get: (id) => [...items.values()].find((item) => item.id === id) || null,
      getAsync: async (id) => [...items.values()].find((item) => item.id === id) || null,
      getByLibraryAndKeyAsync: async (_libraryID, key) => items.get(key) || null,
    },
    Libraries: { get: () => ({ editable: true }) },
    Reader: {},
    SDT: {},
    Styles: { get: () => ({ styleID: "style" }) },
    QuickCopy: { getContentFromItems: () => ({ text: "text", html: "<p>text</p>" }) },
    Tags: { getColors: () => new Map() },
    getMainWindow: () => null,
    debug: () => {},
    logError: () => {},
    ...overrides.Zotero,
  };
  const context = vm.createContext({
    ChromeUtils: overrides.ChromeUtils,
    Zotero: zotero,
    console,
    setTimeout,
    clearTimeout,
  });
  const source = fs.readFileSync(bridgePath, "utf8");
  const exports = [
    "parseBody",
    "internalError",
    "readerCapabilities",
    "contextEndpointClass",
    "renderEndpointClass",
    "navigateEndpointClass",
    "loadSDTDocument",
    "materializedSDTSegments",
    "documentSegmentsEndpointClass",
    "annotationEndpointClass",
    "annotationNoteEndpointClass",
    "tagImpact",
    "tagRenameEndpointClass",
    "tagMergeEndpointClass",
    "exactVersionMap",
    "itemMergeEndpointClass",
  ];
  const expose = exports
    .map((name) => `${name}: typeof ${name} === "function" ? ${name} : null`)
    .join(",");
  vm.runInContext(`${source}\nglobalThis.__bridge = {${expose}};`, context, { filename: bridgePath });
  return { api: context.__bridge, endpoints, items, Zotero: zotero };
}

function endpoint(Endpoint, body, request = {}) {
  const instance = new Endpoint();
  instance._parseJSONBody = request.parse || (() => body);
  return instance.run({ libraryID: 1, data: "", ...request });
}

function responseBody(response) {
  return JSON.parse(response[2]);
}

test("malformed JSON is a stable 400 JSON error", async () => {
  const { api } = loadBridge();
  const result = await endpoint(api.renderEndpointClass(), null, {
    parse: () => { throw new SyntaxError("bad json"); },
  });
  assert.equal(result[0], 400);
  assert.equal(result[1], "application/json");
  assert.equal(responseBody(result).error, "invalid-request");
});

test("reader reports SDT reading separately from annotation creation", () => {
  const { api } = loadBridge({ Zotero: { SDT: { getReader() {} } } });
  assert.deepEqual(
    JSON.parse(JSON.stringify(api.readerCapabilities({}, "pdf"))),
    { sdt: true, createAnnotationFromSDT: false, highlight: false, underline: false },
  );
});

test("render sends citation mode through Zotero QuickCopy", async () => {
  const item = makeItem("ITEM0001");
  let call;
  const { api } = loadBridge({
    items: new Map([[item.key, item]]),
    Zotero: {
      Styles: { get: (id) => id === "style" ? { styleID: id } : null },
      QuickCopy: {
        getContentFromItems(items, format, callback, modified) {
          call = { items, format, callback, modified };
          return { text: "(Example, 2026)", html: "<span>(Example, 2026)</span>" };
        },
      },
    },
  });
  const result = await endpoint(api.renderEndpointClass(), {
    itemKeys: [item.key], style: "style", locale: "en-US", mode: "citation",
  });
  assert.equal(result[0], 200);
  assert.equal(call.modified, true);
  assert.equal(call.format.mode, "bibliography");
  assert.equal(call.format.locale, "en-US");
  assert.equal(responseBody(result).text, "(Example, 2026)");
});

test("render accepts the helper's empty default locale", async () => {
  const item = makeItem("ITEM0001");
  const { api } = loadBridge({ items: new Map([[item.key, item]]) });
  const result = await endpoint(api.renderEndpointClass(), {
    itemKeys: [item.key], style: "style", locale: "", mode: "bibliography",
  });
  assert.equal(result[0], 200);
});

test("render rejects missing items without calling QuickCopy", async () => {
  let called = false;
  const { api } = loadBridge({
    Zotero: { QuickCopy: { getContentFromItems: () => { called = true; } } },
  });
  const result = await endpoint(api.renderEndpointClass(), {
    itemKeys: ["MISSING1"], style: "style", mode: "bibliography",
  });
  assert.equal(result[0], 404);
  assert.equal(responseBody(result).error, "item-not-found");
  assert.equal(called, false);
});

test("navigate reveals a regular item", async () => {
  const item = makeItem("ITEM0001", { id: 42 });
  let selected;
  const { api } = loadBridge({
    items: new Map([[item.key, item]]),
    Zotero: { getMainWindow: () => ({ ZoteroPane: { selectItem: async (id) => { selected = id; } } }) },
  });
  const result = await endpoint(api.navigateEndpointClass(), {
    action: "reveal-item", itemKey: item.key,
  });
  assert.equal(result[0], 200);
  assert.equal(selected, 42);
});

test("navigate opens an annotation at its parent attachment", async () => {
  const attachment = makeItem("PDF00001", { id: 20, isAttachment: () => true });
  const annotation = makeItem("ANN00001", {
    id: 21, parentItemID: 20, isAnnotation: () => true, isRegularItem: () => false,
  });
  let opened;
  const { api } = loadBridge({
    items: new Map([[attachment.key, attachment], [annotation.key, annotation]]),
    Zotero: { Reader: { open: async (...args) => { opened = args; } } },
  });
  const result = await endpoint(api.navigateEndpointClass(), {
    action: "open-annotation", itemKey: annotation.key,
  });
  assert.equal(result[0], 200);
  assert.deepEqual(JSON.parse(JSON.stringify(opened)), [20, { annotationID: "ANN00001" }]);
});

test("native merge requires an exact version map", () => {
  const { api } = loadBridge();
  assert.equal(api.exactVersionMap({ MASTER01: 2, OTHER001: 4 }, ["MASTER01", "OTHER001"]), true);
  assert.equal(api.exactVersionMap({ MASTER01: 2 }, ["MASTER01", "OTHER001"]), false);
  assert.equal(api.exactVersionMap({ MASTER01: 2, OTHER001: 4, EXTRA001: 1 }, ["MASTER01", "OTHER001"]), false);
});

test("native merge commits through Zotero's module and verifies readback", async () => {
  const masterState = { collections: [10], attachments: [20], notes: [] };
  const otherState = { collections: [11], attachments: [], notes: [21] };
  const master = makeItem("MASTER01", {
    version: 2,
    getCollections: () => masterState.collections,
    getAttachments: () => masterState.attachments,
    getNotes: () => masterState.notes,
  });
  const other = makeItem("OTHER001", {
    version: 4,
    getCollections: () => otherState.collections,
    getAttachments: () => otherState.attachments,
    getNotes: () => otherState.notes,
  });
  const { api } = loadBridge({
    items: new Map([[master.key, master], [other.key, other]]),
    ChromeUtils: {
      importESModule: () => ({
        mergeItems: async (target, others) => {
          assert.equal(target, master);
          assert.equal(others.length, 1);
          assert.equal(others[0], other);
          masterState.collections.push(...otherState.collections);
          masterState.attachments.push(...otherState.attachments);
          masterState.notes.push(...otherState.notes);
          target.version++;
          others.forEach((item) => { item.deleted = true; });
        },
      }),
    },
  });
  const result = await endpoint(api.itemMergeEndpointClass(), {
    master: master.key,
    others: [other.key],
    expectedVersions: { MASTER01: 2, OTHER001: 4 },
  });
  assert.equal(result[0], 200);
  assert.deepEqual(responseBody(result), {
    merged: true,
    master: { key: "MASTER01", version: 3 },
    trashed: ["OTHER001"],
  });
});

test("native merge reports missing collections or children after readback", async () => {
  const master = makeItem("MASTER01", {
    version: 2,
    getCollections: () => [10],
    getAttachments: () => [],
    getNotes: () => [],
  });
  const other = makeItem("OTHER001", {
    version: 4,
    getCollections: () => [11],
    getAttachments: () => [20],
    getNotes: () => [21],
  });
  const { api } = loadBridge({
    items: new Map([[master.key, master], [other.key, other]]),
    ChromeUtils: {
      importESModule: () => ({ mergeItems: async (_target, others) => {
        others.forEach((item) => { item.deleted = true; });
      } }),
    },
  });
  const result = await endpoint(api.itemMergeEndpointClass(), {
    master: master.key,
    others: [other.key],
    expectedVersions: { MASTER01: 2, OTHER001: 4 },
  });
  assert.equal(result[0], 500);
  assert.deepEqual(responseBody(result).details, {
    missingCollections: [11],
    missingAttachments: [20],
    missingNotes: [21],
  });
});

test("native merge rejects stale versions before loading the module", async () => {
  const master = makeItem("MASTER01", { version: 3 });
  const other = makeItem("OTHER001", { version: 4 });
  let loaded = false;
  const { api } = loadBridge({
    items: new Map([[master.key, master], [other.key, other]]),
    ChromeUtils: { importESModule: () => { loaded = true; return {}; } },
  });
  const result = await endpoint(api.itemMergeEndpointClass(), {
    master: master.key,
    others: [other.key],
    expectedVersions: { MASTER01: 2, OTHER001: 4 },
  });
  assert.equal(result[0], 412);
  assert.equal(responseBody(result).error, "item-version-changed");
  assert.equal(loaded, false);
});

test("native merge rejects an individually read-only item", async () => {
  const master = makeItem("MASTER01", { version: 2 });
  const other = makeItem("OTHER001", { version: 4, isEditable: () => false });
  const { api } = loadBridge({ items: new Map([[master.key, master], [other.key, other]]) });
  const result = await endpoint(api.itemMergeEndpointClass(), {
    master: master.key,
    others: [other.key],
    expectedVersions: { MASTER01: 2, OTHER001: 4 },
  });
  assert.equal(result[0], 423);
  assert.equal(responseBody(result).error, "item-read-only");
});

test("native merge reports a failed trash readback", async () => {
  const master = makeItem("MASTER01", { version: 2 });
  const other = makeItem("OTHER001", { version: 4 });
  const { api } = loadBridge({
    items: new Map([[master.key, master], [other.key, other]]),
    ChromeUtils: { importESModule: () => ({ mergeItems: async () => {} }) },
  });
  const result = await endpoint(api.itemMergeEndpointClass(), {
    master: master.key,
    others: [other.key],
    expectedVersions: { MASTER01: 2, OTHER001: 4 },
  });
  assert.equal(result[0], 500);
  assert.equal(responseBody(result).error, "merge-readback-failed");
});

module.exports = { endpoint, loadBridge, makeItem, responseBody };
