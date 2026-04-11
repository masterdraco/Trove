import { writable } from "svelte/store";
import type { UserOut } from "$lib/api";

export const currentUser = writable<UserOut | null>(null);
