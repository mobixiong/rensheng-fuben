import { IMAGE_JOB_STATUS, IMAGE_STATUS } from "./constants.js";

export const IMAGE_JOB_TTL_MS = 20 * 60 * 1000;

export function hasImageJobStatus(status) {
  return Object.values(IMAGE_JOB_STATUS).includes(status);
}

export function imageJobStartedAtMs(shot) {
  const job = shot?._image_job || {};
  const raw = Number(job.started_at || job.updated_at || shot?._image_status_started_at || shot?._image_status_updated_at || 0);
  if (!Number.isFinite(raw) || raw <= 0) return 0;
  return raw > 10_000_000_000 ? raw : raw * 1000;
}

export function isFreshImageJob(shot) {
  const startedAt = imageJobStartedAtMs(shot);
  return Boolean(startedAt && Date.now() - startedAt <= IMAGE_JOB_TTL_MS);
}

export function currentImageJobStatus(shot) {
  const jobStatus = shot?._image_job?.status || "";
  if (hasImageJobStatus(jobStatus) && isFreshImageJob(shot)) return jobStatus;
  const legacyStatus = shot?._image_status || "";
  if (hasImageJobStatus(legacyStatus) && isFreshImageJob(shot) && !shot?._image_error) return legacyStatus;
  return "";
}

export function finalImageStatus(shot, hasImage = false) {
  const rawStatus = shot?._image_status || "";
  if (rawStatus === IMAGE_STATUS.policyError) return IMAGE_STATUS.policyError;
  if (rawStatus === IMAGE_STATUS.error) return IMAGE_STATUS.error;
  if (rawStatus === IMAGE_STATUS.done || hasImage) return IMAGE_STATUS.done;
  return IMAGE_STATUS.pending;
}

export function setImageJob(shot, status, options = {}) {
  if (!shot || !hasImageJobStatus(status)) return;
  const now = Date.now();
  const existingJob = shot._image_job || {};
  const shouldPreserveStartedAt = options.preserveStartedAt === true
    && existingJob.status === status
    && existingJob.started_at;
  shot._image_job = {
    ...existingJob,
    status,
    attempt: options.attempt ?? shot._image_job?.attempt ?? 1,
    started_at: options.startedAt || (shouldPreserveStartedAt ? existingJob.started_at : now),
    updated_at: now,
  };
  delete shot._image_status_started_at;
  delete shot._image_status_updated_at;
}

export function clearImageJob(shot) {
  if (!shot) return;
  delete shot._image_job;
  delete shot._image_attempt;
  delete shot._image_status_started_at;
  delete shot._image_status_updated_at;
}

export function setImageFinalStatus(shot, status) {
  if (!shot) return;
  shot._image_status = status;
}

export function clearImageError(shot) {
  if (!shot) return;
  delete shot._image_error;
  delete shot._image_error_code;
  delete shot._image_error_category;
}
