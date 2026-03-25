export function flattenErrors(errorPayload) {
  const messages = [];

  function walk(node, prefix = "") {
    if (!node) {
      return;
    }
    if (Array.isArray(node)) {
      node.forEach((item) => walk(item, prefix));
      return;
    }
    if (typeof node === "object") {
      Object.entries(node).forEach(([key, value]) => {
        walk(value, prefix ? `${prefix}.${key}` : key);
      });
      return;
    }
    if (typeof node === "string") {
      messages.push(prefix ? `${prefix}: ${node}` : node);
    }
  }

  walk(errorPayload);
  return messages;
}
