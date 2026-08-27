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
    Components: overrides.Components,
    Zotero: zotero,
    console,
    setTimeout,
    clearTimeout,
  });
  const source = fs.readFileSync(bridgePath, "utf8");
  const exports = [
    "parseBody",
    "internalError",
    "annotationCompatibility",
    "readerCapabilities",
    "contextEndpointClass",
    "renderEndpointClass",
    "navigateEndpointClass",
    "loadSDTDocument",
    "materializedSDTSegments",
    "documentSegmentsEndpointClass",
    "annotationsEndpointClass",
    "annotationNoteEndpointClass",
    "buildPrivateSDTAnnotation",
    "createPrivateSDTAnnotation",
    "unwrapReaderValue",
    "sameAnnotationPosition",
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

test("reader reports the experimental private annotation backend", () => {
  const reader = {
    _iframeWindow: {},
    _internalReader: {
      _loadSDT() {},
      _getSourceAnnotationMeta() {},
      _annotationManager: { addAnnotation() {} },
    },
  };
  const { api } = loadBridge({
    Components: { utils: { cloneInto: (value) => value } },
    Zotero: { version: "10.0.1", SDT: { getReader() {} } },
  });
  const capabilities = JSON.parse(JSON.stringify(api.readerCapabilities(reader, "pdf")));
  assert.equal(capabilities.sdt, true);
  assert.equal(capabilities.createAnnotationFromSDT, true);
  assert.equal(capabilities.highlight, true);
  assert.equal(capabilities.underline, true);
  assert.equal(capabilities.annotation.experimental, true);
  assert.equal(capabilities.annotation.backend, "private-reader-internals");
  assert.deepEqual(capabilities.annotation.warnings, []);
});

test("compatibility probe flags a future standard API without changing the current backend", () => {
  const reader = {
    _iframeWindow: {},
    _internalReader: {
      _primaryView: { createAnnotationFromSDT() {} },
      _loadSDT() {},
      _getSourceAnnotationMeta() {},
      _annotationManager: { addAnnotation() {} },
    },
  };
  const { api } = loadBridge({
    Components: { utils: { cloneInto: (value) => value } },
    Zotero: { version: "10.0.2" },
  });
  const compatibility = api.annotationCompatibility(reader);
  assert.equal(compatibility.backend, "private-reader-internals");
  assert.equal(compatibility.standardAvailable, true);
  assert.equal(compatibility.warnings.length, 2);
  assert.match(compatibility.warnings.join("\n"), /tested with Zotero 10\.0\.1/);
  assert.match(compatibility.warnings.join("\n"), /use it as primary/);
});

test("compatibility probe names missing private Reader methods", () => {
  const { api } = loadBridge({
    Components: { utils: { cloneInto: (value) => value } },
    Zotero: { version: "10.0.1" },
  });
  const compatibility = api.annotationCompatibility({ _iframeWindow: {}, _internalReader: {} });
  assert.equal(compatibility.privateAPI.state, "incompatible");
  assert.deepEqual(
    JSON.parse(JSON.stringify(compatibility.privateAPI.missing)),
    [
      "reader._internalReader._loadSDT",
      "reader._internalReader._getSourceAnnotationMeta",
      "reader._internalReader._annotationManager.addAnnotation",
    ],
  );
});

test("private annotation adapter unwraps cross-compartment SDT values", async () => {
  const mapper = {
    sdtToSourcePosition: () => ({ pageIndex: 2, rects: [[1, 2, 3, 4]] }),
    transformAnnotationPosition: (position) => position,
  };
  const internalReader = {
    _loadSDT: async () => ({ wrappedJSObject: { mapper } }),
    _getSourceAnnotationMeta: () => ({ sortIndex: "00002|000000|00000", pageLabel: "3" }),
    _annotationManager: { addAnnotation() {} },
  };
  const reader = { _iframeWindow: {}, _internalReader: internalReader };
  const { api } = loadBridge({
    Components: {
      utils: {
        cloneInto: (value) => value,
        waiveXrays: (value) => value.wrappedJSObject || value,
      },
    },
    Zotero: { version: "10.0.1" },
  });
  const built = await api.buildPrivateSDTAnnotation(
    { reader, internalReader },
    { start: [5, 0, 0], end: [5, 0, 7] },
    "highlight",
    "Missing",
  );
  assert.equal(built.position.pageIndex, 2);
  assert.equal(built.text, "Missing");
  assert.equal(built.pageLabel, "3");
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

test("SDT loading passes the attachment ID to Zotero's reader", async () => {
  const attachment = makeItem("PDF00001", { id: 77 });
  let call;
  const document = { metadata: { source: { hash: "hash" } }, content: [] };
  const { api } = loadBridge({
    Zotero: {
      SDT: {
        async getReader(...args) {
          call = args;
          return { materialize: async () => document };
        },
      },
    },
  });
  assert.equal(await api.loadSDTDocument(attachment), document);
  assert.deepEqual(JSON.parse(JSON.stringify(call)), [77, { isPriority: true }]);
});

test("SDT materialization emits one segment per leaf block", () => {
  const { api } = loadBridge();
  const document = {
    content: [
      {
        type: "section",
        flowClass: "body",
        content: [
          { type: "paragraph", content: [{ text: "Hello " }, { text: "world" }] },
          { type: "paragraph", content: [{ text: "Second" }] },
        ],
      },
      { type: "paragraph", flowClass: "excluded", content: [{ text: "Auxiliary" }] },
    ],
  };
  const segments = JSON.parse(JSON.stringify(api.materializedSDTSegments(document)));
  assert.deepEqual(segments.map(({ id, text }) => ({ id, text })), [
    { id: "block:0.0", text: "Hello world" },
    { id: "block:0.1", text: "Second" },
  ]);
  assert.deepEqual(segments[0].spans.map((span) => span.ref), [[0, 0, 0], [0, 0, 1]]);
  assert.equal(api.materializedSDTSegments(document, true).length, 3);
});

test("annotation endpoint rejects the internal raw RefPath shape", async () => {
  const attachment = makeItem("PDF00001", {
    id: 77,
    libraryID: 1,
    isAttachment: () => true,
    getAnnotations: () => [],
  });
  const view = { initializedPromise: Promise.resolve(), createAnnotationFromSDT() {} };
  const reader = {
    itemID: 77,
    type: "pdf",
    _initPromise: Promise.resolve(),
    _internalReader: { _primaryView: view },
  };
  const { api } = loadBridge({
    items: new Map([[attachment.key, attachment]]),
    Zotero: {
      getMainWindow: () => ({ Zotero_Tabs: { selectedType: "reader", selectedID: "tab" } }),
      Reader: { getByTabID: () => reader },
    },
  });
  const result = await endpoint(api.annotationsEndpointClass(), {
    attachmentKey: attachment.key,
    type: "highlight",
    target: { kind: "sdt", start: [0, -1], end: [0, 2] },
  });
  assert.equal(result[0], 400);
  assert.equal(responseBody(result).error, "invalid-target");
});

test("annotation deduplication includes the native source position", async () => {
  const annotations = [];
  const existing = makeItem("OLD00001", { annotationType: "highlight" });
  const trashed = makeItem("TRASH001", { annotationType: "highlight", deleted: true });
  const created = makeItem("NEW00001");
  annotations.push(existing, trashed);
  const attachment = makeItem("PDF00001", {
    id: 77,
    libraryID: 1,
    isAttachment: () => true,
    getAnnotations: () => annotations,
  });
  const document = {
    metadata: { source: { hash: "hash" } },
    content: [{ type: "paragraph", content: [{ text: "Hello" }] }],
  };
  const positions = {
    OLD00001: { pageIndex: 0 },
    TRASH001: { pageIndex: 1, rects: [[1.234, 2, 3, 4]] },
    NEW00001: { pageIndex: 1 },
  };
  let addCalls = 0;
  const view = { initializedPromise: Promise.resolve() };
  const mapper = {
    sdtToSourcePosition: () => ({ pageIndex: 1, rects: [[1.23449, 2, 3, 4]] }),
    transformAnnotationPosition: (position) => position,
  };
  const internalReader = {
    _primaryView: view,
    _loadSDT: async () => ({ structure: document, mapper }),
    _getSourceAnnotationMeta: () => ({ sortIndex: "00000|000000|00000", pageLabel: "1" }),
    _annotationManager: {
      addAnnotation(payload) {
        addCalls++;
        positions[created.key] = payload.position;
        annotations.push(created);
        setTimeout(() => {
          created.annotationType = "highlight";
          created.annotationPosition = JSON.stringify(payload.position);
        }, 10);
        return { id: created.key };
      },
    },
  };
  const reader = {
    itemID: 77,
    type: "pdf",
    _initPromise: Promise.resolve(),
    _iframeWindow: {},
    _internalReader: internalReader,
  };
  const { api } = loadBridge({
    items: new Map([[attachment.key, attachment]]),
    Components: { utils: { cloneInto: (value) => value } },
    Zotero: {
      SDT: { getReader: async () => ({ materialize: async () => document }) },
      Annotations: {
        toJSONSync: (annotation) => ({
          key: annotation.key,
          type: "highlight",
          text: "Hello",
          comment: "",
          color: "#ffd400",
          position: positions[annotation.key],
        }),
      },
      getMainWindow: () => ({ Zotero_Tabs: { selectedType: "reader", selectedID: "tab" } }),
      Reader: { getByTabID: () => reader },
    },
  });
  const stale = await endpoint(api.annotationsEndpointClass(), {
    attachmentKey: attachment.key,
    sourceHash: "stale-hash",
    type: "highlight",
    target: { segmentId: "block:0", start: 0, end: 5 },
  });
  assert.equal(stale[0], 412);
  assert.equal(responseBody(stale).error, "document-changed");
  assert.equal(addCalls, 0);

  const result = await endpoint(api.annotationsEndpointClass(), {
    attachmentKey: attachment.key,
    sourceHash: "hash",
    type: "highlight",
    target: { segmentId: "block:0", start: 0, end: 5 },
  });
  assert.equal(result[0], 200);
  assert.equal(responseBody(result).created, true);
  assert.equal(responseBody(result).annotation.key, "NEW00001");
  assert.equal(responseBody(result).annotation.type, "highlight");
  assert.equal(responseBody(result).annotation.text, "Hello");
  assert.deepEqual(
    JSON.parse(JSON.stringify(responseBody(result).annotation.position)),
    { pageIndex: 1, rects: [[1.23449, 2, 3, 4]] },
  );

  positions[created.key] = { pageIndex: 1, rects: [[1.234, 2, 3, 4]] };
  const duplicate = await endpoint(api.annotationsEndpointClass(), {
    attachmentKey: attachment.key,
    sourceHash: "hash",
    type: "highlight",
    target: { segmentId: "block:0", start: 0, end: 5 },
  });
  assert.equal(duplicate[0], 200);
  assert.equal(responseBody(duplicate).created, false);
  assert.equal(responseBody(duplicate).duplicate, true);
  assert.equal(addCalls, 1);
});

test("annotation endpoint reports private mapper drift explicitly", async () => {
  const attachment = makeItem("PDF00001", {
    id: 77,
    libraryID: 1,
    isAttachment: () => true,
    getAnnotations: () => [],
  });
  const document = {
    metadata: { source: { hash: "hash" } },
    content: [{ type: "paragraph", content: [{ text: "Hello" }] }],
  };
  const internalReader = {
    _primaryView: { initializedPromise: Promise.resolve() },
    _loadSDT: async () => ({ structure: document, mapper: { sdtToSourcePosition() {} } }),
    _getSourceAnnotationMeta() {},
    _annotationManager: { addAnnotation() {} },
  };
  const reader = {
    itemID: 77,
    type: "pdf",
    _initPromise: Promise.resolve(),
    _iframeWindow: {},
    _internalReader: internalReader,
  };
  const { api } = loadBridge({
    items: new Map([[attachment.key, attachment]]),
    Components: { utils: { cloneInto: (value) => value } },
    Zotero: {
      version: "10.0.1",
      SDT: { getReader: async () => ({ materialize: async () => document }) },
      getMainWindow: () => ({ Zotero_Tabs: { selectedType: "reader", selectedID: "tab" } }),
      Reader: { getByTabID: () => reader },
    },
  });
  const result = await endpoint(api.annotationsEndpointClass(), {
    attachmentKey: attachment.key,
    sourceHash: "hash",
    type: "underline",
    target: { segmentId: "block:0", start: 0, end: 5 },
  });
  assert.equal(result[0], 501);
  assert.equal(responseBody(result).error, "annotation-backend-incompatible");
  assert.deepEqual(
    JSON.parse(JSON.stringify(responseBody(result).details.missing)),
    ["sdt.mapper.transformAnnotationPosition"],
  );
});

test("annotation-note rejects duplicate keys and a read-only parent", async () => {
  const parent = makeItem("ITEM0001", { isEditable: () => false });
  const { api } = loadBridge({ items: new Map([[parent.key, parent]]) });
  const DuplicateEndpoint = api.annotationNoteEndpointClass();
  const duplicate = await endpoint(DuplicateEndpoint, {
    parentItemKey: parent.key,
    annotationKeys: ["ANN00001", "ANN00001"],
  });
  assert.equal(duplicate[0], 400);
  assert.equal(responseBody(duplicate).error, "invalid-annotation-keys");

  const readOnly = await endpoint(api.annotationNoteEndpointClass(), {
    parentItemKey: parent.key,
    annotationKeys: ["ANN00001"],
  });
  assert.equal(readOnly[0], 423);
  assert.equal(responseBody(readOnly).error, "library-read-only");
});

test("tag impact ignores a same-named tag that exists only in another library", async () => {
  const { api } = loadBridge({
    Zotero: {
      Tags: {
        getID: () => 9,
        getTagItems: async () => [],
        getColors: () => new Map(),
      },
    },
  });
  const impact = await api.tagImpact(1, "Elsewhere");
  assert.equal(impact.tagID, 9);
  assert.equal(impact.exists, false);
  assert.equal(impact.itemIDs.length, 0);
});

test("tag rename preserves an existing uncolored target", async () => {
  const calls = [];
  const ids = { Legacy: 1, Current: 2 };
  const { api } = loadBridge({
    Zotero: {
      Tags: {
        getID: (name) => ids[name] || null,
        getTagItems: async (_libraryID, id) => id === 1 ? [10] : [20],
        getColors: () => new Map(),
        rename: async (...args) => calls.push(["rename", ...args]),
        setColor: async (...args) => calls.push(["setColor", ...args]),
      },
    },
  });
  const result = await endpoint(api.tagRenameEndpointClass(), {
    from: "Legacy", to: "Current", expectedCount: 1,
  });
  assert.equal(result[0], 200);
  assert.equal(responseBody(result).targetExisted, true);
  assert.deepEqual(calls, [
    ["rename", 1, "Legacy", "Current"],
    ["setColor", 1, "Current", false],
  ]);
});

test("tag rename rejects a stale impact count before mutation", async () => {
  let renamed = false;
  const { api } = loadBridge({
    Zotero: {
      Tags: {
        getID: () => 1,
        getTagItems: async () => [10, 20],
        getColors: () => new Map(),
        rename: async () => { renamed = true; },
      },
    },
  });
  const result = await endpoint(api.tagRenameEndpointClass(), {
    from: "Legacy", to: "Current", expectedCount: 1,
  });
  assert.equal(result[0], 412);
  assert.equal(responseBody(result).error, "tag-impact-changed");
  assert.equal(renamed, false);
});

test("tag merge uses the first colored source only when the target is absent", async () => {
  const calls = [];
  const ids = { Legacy: 1, Old: 2 };
  const colors = new Map([["Legacy", { color: "#FF0000", position: 3 }]]);
  const { api } = loadBridge({
    Zotero: {
      Tags: {
        getID: (name) => ids[name] || null,
        getTagItems: async (_libraryID, id) => id ? [id * 10] : [],
        getColors: () => colors,
        rename: async (...args) => calls.push(["rename", ...args]),
        setColor: async (...args) => calls.push(["setColor", ...args]),
      },
    },
  });
  const result = await endpoint(api.tagMergeEndpointClass(), {
    into: "Current",
    sources: [
      { name: "Legacy", expectedCount: 1 },
      { name: "Old", expectedCount: 1 },
    ],
    colorPolicy: "preserve-target",
  });
  assert.equal(result[0], 200);
  assert.equal(responseBody(result).targetExisted, false);
  assert.deepEqual(calls.filter(([name]) => name === "setColor"), [
    ["setColor", 1, "Current", "#FF0000", 3],
    ["setColor", 1, "Current", "#FF0000", 3],
  ]);
});

module.exports = { endpoint, loadBridge, makeItem, responseBody };
