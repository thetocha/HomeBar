const MAX_EDGE = 960;
const QUALITY = 0.82;
const SKIP_BELOW_BYTES = 180_000;

/** Downscale a camera photo in the browser so the upload is a few hundred KB, not several MB. */
export async function preparePhoto(file: File): Promise<File> {
  if (!file.type.startsWith("image/") || file.type === "image/gif") return file;
  if (file.type === "image/jpeg" && file.size < SKIP_BELOW_BYTES) return file;
  try {
    const bitmap = await decodeScaled(file);
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.type === "image/jpeg" && file.size < SKIP_BELOW_BYTES * 2) {
      bitmap.close();
      return file;
    }
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) {
      bitmap.close();
      return file;
    }
    ctx.imageSmoothingQuality = "medium";
    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob((result) => resolve(result), "image/jpeg", QUALITY);
    });
    if (!blob || blob.size >= file.size) return file;
    const stem = file.name.replace(/\.[^.]+$/, "") || "photo";
    return new File([blob], `${stem}.jpg`, { type: "image/jpeg", lastModified: Date.now() });
  } catch {
    return file;
  }
}

async function decodeScaled(file: File): Promise<ImageBitmap> {
  const options: ImageBitmapOptions = { imageOrientation: "from-image", resizeQuality: "medium" };
  const geometry = await jpegGeometry(file);
  if (geometry) {
    const longest = Math.max(geometry.width, geometry.height);
    if (longest > MAX_EDGE) {
      if (geometry.width >= geometry.height) options.resizeWidth = MAX_EDGE;
      else options.resizeHeight = MAX_EDGE;
    }
  }
  try {
    return await createImageBitmap(file, options);
  } catch {
    return await createImageBitmap(file);
  }
}

async function jpegGeometry(file: File): Promise<{ width: number; height: number } | null> {
  const name = file.name.toLowerCase();
  const looksJpeg = file.type === "image/jpeg" || name.endsWith(".jpg") || name.endsWith(".jpeg");
  if (!looksJpeg) return null;
  const bytes = new Uint8Array(await file.slice(0, 512 * 1024).arrayBuffer());
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) return null;
  let orientation = 1;
  let offset = 2;
  while (offset + 9 < bytes.length) {
    if (bytes[offset] !== 0xff) return null;
    const marker = bytes[offset + 1];
    if (marker === 0xd8 || marker === 0x01) {
      offset += 2;
      continue;
    }
    if (marker === 0xd9 || marker === 0xda) return null;
    const length = (bytes[offset + 2] << 8) | bytes[offset + 3];
    if (length < 2 || offset + 2 + length > bytes.length) return null;
    if (marker === 0xe1) orientation = readExifOrientation(bytes, offset + 4, length - 2) ?? orientation;
    if (marker === 0xc0 || marker === 0xc1 || marker === 0xc2) {
      const height = (bytes[offset + 5] << 8) | bytes[offset + 6];
      const width = (bytes[offset + 7] << 8) | bytes[offset + 8];
      if (orientation >= 5 && orientation <= 8) return { width: height, height: width };
      return { width, height };
    }
    offset += 2 + length;
  }
  return null;
}

function readExifOrientation(bytes: Uint8Array, start: number, length: number): number | null {
  if (length < 16) return null;
  if (bytes[start] !== 0x45 || bytes[start + 1] !== 0x78 || bytes[start + 2] !== 0x69 || bytes[start + 3] !== 0x66) {
    return null;
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset + start + 6, length - 6);
  const little = view.getUint8(0) === 0x49;
  const u16 = (offset: number) => view.getUint16(offset, little);
  const u32 = (offset: number) => view.getUint32(offset, little);
  if (u16(2) !== 42) return null;
  const ifd = u32(4);
  if (ifd + 2 > view.byteLength) return null;
  const count = u16(ifd);
  for (let i = 0; i < count; i += 1) {
    const entry = ifd + 2 + i * 12;
    if (entry + 12 > view.byteLength) return null;
    if (u16(entry) === 0x0112) return u16(entry + 8);
  }
  return null;
}
