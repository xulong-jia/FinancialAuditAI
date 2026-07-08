import { readFileSync } from "node:fs";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const root = new URL("..", import.meta.url).pathname;

function readSource(path) {
  return readFileSync(join(root, path), "utf8");
}

test("auth client exposes local demo registration endpoint", () => {
  const source = readSource("src/api/client.ts");

  assert.match(source, /export function register/);
  assert.match(source, /\/api\/v1\/auth\/register/);
  assert.match(source, /body\?\.error\?\.message/);
});

test("login screen exposes create account flow with basic validation", () => {
  const source = readSource("src/App.tsx");

  assert.match(source, /注册账号/);
  assert.match(source, /handleRegister/);
  assert.match(source, /confirm_password/);
  assert.match(source, /密码至少 8 位/);
  assert.match(source, /两次输入的密码不一致/);
  assert.match(source, /setAccessToken\(token\.access_token\)/);
});
