const DEFAULT_MAX_DIMENSION = 1920;
const DEFAULT_TARGET_BYTES = 800_000; // ~0.8 MB
const DEFAULT_MIN_BYTES = 500_000; // ~0.5 MB
const MIN_QUALITY = 0.4;
const QUALITY_STEP = 0.08;

export type CompressionResult = {
  file: File;
  width: number;
  height: number;
  originalSize: number;
  compressedSize: number;
  skipped: boolean;
  reason?: string;
};

export type CompressionOptions = {
  /**
   * Maximum allowed longest edge. Anything larger will be scaled down.
   */
  maxDimension?: number;
  /**
   * Target upper bound for bytes. The compressor will reduce quality toward this target.
   */
  targetBytes?: number;
  /**
   * Threshold under which we skip compression when dimensions are already within bounds.
   */
  skipBelowBytes?: number;
  /**
   * Force output mime type. Defaults to JPEG for most cases.
   */
  outputMimeType?: string;
};

export const isImageFile = (file: File) => file.type.startsWith("image/");

const getExtension = (mime: string) => {
  const [, ext] = mime.split("/");
  return ext ? ext.split("+")[0] : "jpg";
};

const loadImage = (file: File) =>
  new Promise<HTMLImageElement>((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = (err) => {
      URL.revokeObjectURL(url);
      reject(err);
    };
    img.src = url;
  });

const canvasFromImage = (
  img: HTMLImageElement,
  orientation: number,
  targetWidth: number,
  targetHeight: number,
) => {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("Could not create canvas context");
  }

  // Handle orientation transforms.
  let width = targetWidth;
  let height = targetHeight;
  if (orientation >= 5 && orientation <= 8) {
    canvas.width = targetHeight;
    canvas.height = targetWidth;
  } else {
    canvas.width = targetWidth;
    canvas.height = targetHeight;
  }

  ctx.save();
  switch (orientation) {
    case 2:
      ctx.translate(canvas.width, 0);
      ctx.scale(-1, 1);
      break;
    case 3:
      ctx.translate(canvas.width, canvas.height);
      ctx.rotate(Math.PI);
      break;
    case 4:
      ctx.translate(0, canvas.height);
      ctx.scale(1, -1);
      break;
    case 5:
      ctx.rotate(0.5 * Math.PI);
      ctx.scale(1, -1);
      break;
    case 6:
      ctx.rotate(0.5 * Math.PI);
      ctx.translate(0, -canvas.width);
      break;
    case 7:
      ctx.rotate(0.5 * Math.PI);
      ctx.translate(canvas.height, -canvas.width);
      ctx.scale(-1, 1);
      break;
    case 8:
      ctx.rotate(-0.5 * Math.PI);
      ctx.translate(-canvas.height, 0);
      break;
    default:
      break;
  }

  ctx.drawImage(img, 0, 0, width, height);
  ctx.restore();
  return canvas;
};

const canvasToBlob = (
  canvas: HTMLCanvasElement,
  mimeType: string,
  quality: number,
): Promise<Blob> =>
  new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error("Compression failed"));
          return;
        }
        resolve(blob);
      },
      mimeType,
      quality,
    );
  });

const pickOutputMime = (inputType: string, requested?: string) => {
  if (requested) return requested;
  if (inputType === "image/webp" || inputType === "image/jpeg") return inputType;
  return "image/jpeg";
};

export async function compressImageFile(
  file: File,
  options: CompressionOptions = {},
): Promise<CompressionResult> {
  if (!isImageFile(file)) {
    return {
      file,
      width: 0,
      height: 0,
      originalSize: file.size,
      compressedSize: file.size,
      skipped: true,
      reason: "not-image",
    };
  }

  const maxDimension = options.maxDimension ?? DEFAULT_MAX_DIMENSION;
  const targetBytes = options.targetBytes ?? DEFAULT_TARGET_BYTES;
  const skipBelowBytes = options.skipBelowBytes ?? DEFAULT_MIN_BYTES;
  // Browsers already respect EXIF orientation when decoding images; forcing our own
  // rotation can double-rotate portrait photos. Always treat orientation as "normal".
  const orientation = 1;
  const img = await loadImage(file);
  const origWidth = img.naturalWidth || img.width;
  const origHeight = img.naturalHeight || img.height;
  const longestEdge = Math.max(origWidth, origHeight);
  const scale =
    longestEdge > maxDimension ? maxDimension / longestEdge : Math.max(1, longestEdge / maxDimension);
  const targetWidth = Math.max(1, Math.round(origWidth * scale));
  const targetHeight = Math.max(1, Math.round(origHeight * scale));

  // Skip when already small and within bounds.
  if (longestEdge <= maxDimension && file.size <= skipBelowBytes && orientation === 1) {
    return {
      file,
      width: origWidth,
      height: origHeight,
      originalSize: file.size,
      compressedSize: file.size,
      skipped: true,
      reason: "already-small",
    };
  }

  const outputMime = pickOutputMime(file.type, options.outputMimeType);
  const canvas = canvasFromImage(img, orientation, targetWidth, targetHeight);

  let quality = 0.82;
  let blob = await canvasToBlob(canvas, outputMime, quality);
  while (blob.size > targetBytes && quality > MIN_QUALITY + QUALITY_STEP) {
    quality = Math.max(MIN_QUALITY, quality - QUALITY_STEP);
    // eslint-disable-next-line no-await-in-loop
    blob = await canvasToBlob(canvas, outputMime, quality);
  }

  const ext = getExtension(outputMime);
  const baseName = file.name.replace(/\.[^.]+$/, "");
  const newFile = new File([blob], `${baseName || "upload"}-compressed.${ext}`, {
    type: outputMime,
    lastModified: Date.now(),
  });

  return {
    file: newFile,
    width: canvas.width,
    height: canvas.height,
    originalSize: file.size,
    compressedSize: newFile.size,
    skipped: false,
    reason: blob.size <= targetBytes ? "compressed" : "size-floor-reached",
  };
}
