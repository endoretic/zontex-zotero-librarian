const STATUS_ROUTE = "/api/users/:userID/zotero-modified/statuses";
const STYLES_ROUTE = "/api/users/:userID/zotero-modified/styles";
const ROUTES = [STATUS_ROUTE, STYLES_ROUTE];
let bridgeVersion = "unknown";

function jsonResponse(status, value) {
  return [status, "application/json", JSON.stringify(value, null, 2)];
}

function textResponse(status, value) {
  return [status, "text/plain", String(value)];
}

function parseBody(endpoint, requestData) {
  let body = endpoint._parseJSONBody(requestData.data);
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new Error("Request body must be a JSON object");
  }
  return body;
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

async function startup(data) {
  bridgeVersion = data && data.version ? String(data.version) : "unknown";
  await Zotero.initializationPromise;
  Zotero.Server.Endpoints[STATUS_ROUTE] = statusEndpointClass();
  Zotero.Server.Endpoints[STYLES_ROUTE] = stylesEndpointClass();
  Zotero.debug(`Zotero Modified Bridge ${bridgeVersion} started`);
}

function shutdown() {
  for (let route of ROUTES) delete Zotero.Server.Endpoints[route];
  bridgeVersion = "unknown";
}

function install() {}
function uninstall() {}
