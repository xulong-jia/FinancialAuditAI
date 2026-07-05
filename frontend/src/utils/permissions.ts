import type { UserRecord } from "../types/api";

export function hasPermission(user: UserRecord | null, permission: string): boolean {
  if (!user) {
    return false;
  }
  return user.permissions.includes("*") || user.permissions.includes(permission);
}
