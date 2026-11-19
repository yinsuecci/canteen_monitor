import { readFile, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const lock = JSON.parse(await readFile('package-lock.json', 'utf8'));
const sections = ['Third-party license notices\nGenerated from installed production dependencies.\n'];
for (const [path, entry] of Object.entries(lock.packages)) {
  if (!path || entry.dev) continue;
  const directory = resolve(path);
  const pkg = JSON.parse(await readFile(resolve(directory, 'package.json'), 'utf8'));
  const files = (await readdir(directory)).filter(name => /^(license|notice|copyrightnotice)(\.|$)/i.test(name)).sort();
  if (!files.some(name => /^license(\.|$)/i.test(name))) {
    throw new Error(`Missing license text for ${pkg.name}`);
  }
  sections.push(`\n=== ${pkg.name} ${pkg.version} ===\n`);
  for (const name of files) {
    sections.push(`${name}\n${await readFile(resolve(directory, name), 'utf8')}\n`);
  }
}
await writeFile('dist/THIRD_PARTY_LICENSES.txt', sections.join('\n'), 'utf8');
