"use server";

import { revalidatePath } from "next/cache";
import { adminFetch } from "@/lib/admin";

async function boardAction(action: "recrawl" | "enable" | "disable", form: FormData) {
  const id = String(form.get("id") ?? "");
  if (!/^[0-9a-f-]{36}$/.test(id)) return;
  await adminFetch(`/boards/${id}/${action}`, { method: "POST" });
  revalidatePath("/admin/boards");
}

export async function recrawlBoard(form: FormData) {
  await boardAction("recrawl", form);
}

export async function enableBoard(form: FormData) {
  await boardAction("enable", form);
}

export async function disableBoard(form: FormData) {
  await boardAction("disable", form);
}
