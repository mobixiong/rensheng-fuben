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
  if (rawStatus === IMAGE_STATUS.done || hasImage) return IMAGE_STATUS.done;
  if (rawStatus === IMAGE_STATUS.policyError) return IMAGE_STATUS.policyError;
  if (rawStatus === IMAGE_STATUS.error) return IMAGE_STATUS.error;
  return IMAGE_STATUS.pending;
}

export function hasPolicyImageError(shot) {
  const rawStatus = shot?._image_status || "";
  const errorText = String(shot?._image_error || "");
  return rawStatus === IMAGE_STATUS.policyError
    || shot?._image_error_category === "prompt_policy"
    || errorText.includes("content_policy_violation")
    || errorText.includes("提示词被内容安全策略拦截")
    || errorText.includes("不合规")
    || errorText.includes("防护限制");
}

function activeJobFromOptions(options) {
  const activeJob = options.activeJob && typeof options.activeJob === "object" ? options.activeJob : null;
  const activeStatus = activeJob?.status || options.activeStatus || "";
  if (!hasImageJobStatus(activeStatus)) return null;
  return {
    status: activeStatus,
    attempt: activeJob?.attempt ?? options.attempt ?? "",
  };
}

function resolvedStaticImageStatus(shot, hasImage) {
  if (hasImage) return IMAGE_STATUS.done;
  if (hasPolicyImageError(shot)) return IMAGE_STATUS.policyError;
  if (shot?._image_error) return IMAGE_STATUS.error;
  return finalImageStatus(shot, hasImage);
}

function labelForImageStatus(status) {
  switch (status) {
    case IMAGE_JOB_STATUS.redrawing:
      return "重抽中";
    case IMAGE_JOB_STATUS.generating:
      return "生成中";
    case IMAGE_JOB_STATUS.retrying:
      return "重试中";
    case IMAGE_STATUS.policyError:
      return "提示词不合规";
    case IMAGE_STATUS.error:
      return "失败";
    case IMAGE_STATUS.done:
      return "已完成";
    default:
      return "等待中";
  }
}

function placeholderTextForImageStatus(status, attempt) {
  switch (status) {
    case IMAGE_JOB_STATUS.redrawing:
      return "重抽中";
    case IMAGE_JOB_STATUS.generating:
      return "生成中";
    case IMAGE_JOB_STATUS.retrying:
      return `重试中 ${attempt || ""}`.trim();
    case IMAGE_STATUS.policyError:
      return "提示词不合规<br />请修改后重试";
    case IMAGE_STATUS.error:
      return "生成失败";
    case IMAGE_STATUS.done:
      return "已完成";
    default:
      return "等待生成";
  }
}

function placeholderClassForImageStatus(status, isJobStatus) {
  if (isJobStatus) return " generating";
  if (status === IMAGE_STATUS.policyError) return " policy-error";
  if (status === IMAGE_STATUS.error) return " error";
  return "";
}

function statusClassForImageStatus(status, isJobStatus) {
  if (isJobStatus) return "generating";
  if (status === IMAGE_STATUS.policyError) return "policy-error";
  if (status === IMAGE_STATUS.error) return "error";
  if (status === IMAGE_STATUS.done) return "done";
  return "pending";
}

export function imageDisplayState(shot, options = {}) {
  const hasImage = options.hasImage === true;
  const activeJob = activeJobFromOptions(options);
  const persistedJobStatus = hasImage ? "" : currentImageJobStatus(shot);
  const status = activeJob?.status || persistedJobStatus || resolvedStaticImageStatus(shot, hasImage);
  const isJobStatus = hasImageJobStatus(status);
  const attempt = activeJob?.attempt ?? shot?._image_job?.attempt ?? shot?._image_attempt ?? options.attempt ?? "";
  return {
    status,
    isJobStatus,
    attempt,
    isBusy: isJobStatus,
    statusLabel: labelForImageStatus(status),
    placeholderText: placeholderTextForImageStatus(status, attempt),
    placeholderClass: placeholderClassForImageStatus(status, isJobStatus),
    statusClass: statusClassForImageStatus(status, isJobStatus),
  };
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
