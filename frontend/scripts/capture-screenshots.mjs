import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";

const PORT = 4173;

const variants = [
  { name: "light-desktop", width: 1440, height: 900, theme: "light" },
  { name: "dark-desktop", width: 1440, height: 900, theme: "dark" },
  { name: "light-mobile", width: 390, height: 844, theme: "light" },
  { name: "dark-mobile", width: 390, height: 844, theme: "dark" },
];

const screenshotDir = path.resolve("screenshots");

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function ensurePreviewServer() {
  const command = `npm run preview -- --host --outDir build --port ${PORT} --strictPort`;
  const shell = process.platform === "win32" ? "cmd.exe" : "sh";
  const shellArgs = process.platform === "win32" ? ["/c", command] : ["-c", command];

  const preview = spawn(shell, shellArgs, {
    cwd: process.cwd(),
    stdio: "pipe",
  });

  preview.stdout?.on("data", (chunk) => {
    process.stdout.write(chunk);
  });

  preview.stderr?.on("data", (chunk) => {
    process.stderr.write(chunk);
  });

  await wait(4000);

  return preview;
}

async function capture() {
  await mkdir(screenshotDir, { recursive: true });
  const preview = await ensurePreviewServer();

  try {
    const browser = await chromium.launch();
    for (const variant of variants) {
      const context = await browser.newContext({
        viewport: { width: variant.width, height: variant.height },
        deviceScaleFactor: variant.width < 600 ? 2 : 1,
      });
      const page = await context.newPage();
      await page.goto(`http://127.0.0.1:${PORT}`, { waitUntil: "networkidle" });
      await page.evaluate((theme) => {
        localStorage.setItem("theme", theme);
        document.documentElement.classList.toggle("dark", theme === "dark");
      }, variant.theme);
      await page.reload({ waitUntil: "networkidle" });
      await page.waitForTimeout(1200);
      const targetPath = path.join(screenshotDir, `${variant.name}.png`);
      await page.screenshot({ path: targetPath, fullPage: true });
      console.log(`Captured ${variant.name} → ${targetPath}`);
      await context.close();
    }
    await browser.close();
  } finally {
    preview.kill("SIGINT");
  }
}

capture().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
