import { IMAGE_STATUS } from "./constants.js";

export function introImageSecondsValue(els) {
  const value = Number.parseFloat(els.introImageSeconds?.value || "0.3");
  if (!Number.isFinite(value) || value <= 0) return 0.3;
  return Math.max(0.08, Math.min(3, value));
}

export function createImageProjectId() {
  const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
  const rand = Math.random().toString(16).slice(2, 10);
  return `img_${stamp}_${rand}`;
}

export function mergeShotImageResult(targetStory, sourceStory, index) {
  const sourceShot = sourceStory?.shots?.[index];
  const targetShot = targetStory?.shots?.[index];
  if (!sourceShot || !targetShot) return targetStory;
  for (const key of ["image_path", "image_url", "resolved_image_prompt"]) {
    if (sourceShot[key]) targetShot[key] = sourceShot[key];
  }
  targetShot._image_version = Date.now();
  targetShot._image_status = IMAGE_STATUS.done;
  delete targetShot._image_error;
  if (sourceStory.project_id) targetStory.project_id = sourceStory.project_id;
  return targetStory;
}

export function hasShotImage(shot) {
  return Boolean(shot?.image_url || shot?.image_path);
}

export function normalizeShotIndexes(indexes, shotsLength) {
  const values = indexes instanceof Set ? Array.from(indexes) : Array.isArray(indexes) ? indexes : [indexes];
  return Array.from(new Set(
    values
      .map(Number)
      .filter((index) => Number.isInteger(index) && index >= 0 && index < shotsLength),
  )).sort((a, b) => a - b);
}

export async function runWithConcurrency(items, limit, worker) {
  if (!items.length) return [];
  const results = new Array(items.length);
  const workerCount = Math.min(items.length, Math.max(1, Number(limit) || 1));
  let cursor = 0;

  async function runNext() {
    while (cursor < items.length) {
      const current = cursor;
      cursor += 1;
      try {
        results[current] = { status: "fulfilled", value: await worker(items[current], current) };
      } catch (reason) {
        results[current] = { status: "rejected", reason };
      }
    }
  }

  await Promise.all(Array.from({ length: workerCount }, runNext));
  return results;
}

export function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function clampProgress(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(1, numeric));
}
