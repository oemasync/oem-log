#!/usr/bin/env node
/* Mutation harness for the /about head migration.
 *
 * The test suite has a dead-CSS check that walks every scoped <style>
 * block and flags a selector targeting a class its own file's markup
 * never uses. The /about page carried `.about-head` / `.about-body`
 * / `.about-links` rules whose markup DID use those classes - so the
 * check was green while the page was a second implementation of the
 * library's own head. The check could not see the defect, because it
 * only asks "is this selector dead", not "is this class the library's".
 *
 * So the guard here is a SOURCE check, not a CSS check: the library
 * owns `.cm-head`, and a page that styles its own head-shaped block
 * under a different name is a fork. Each mutant reverts one half of
 * the migration and requires the suite to fail.
 *
 * Mutants are DERIVED from the file rather than written as literal
 * strings: the harness reads the current markup, and each mutant is
 * built by a transform on a substring it found. A mutant whose pattern
 * is absent is reported as SKIP and the run exits non-zero - a miss
 * that looks like a pass is worse than no test at all.
 *
 * Run: node tests/mutate-about.mjs
 */
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const about = join(root, 'src/pages/about.astro');
const run = () => spawnSync('node', ['--test', 'tests/blog.test.mjs'], { encoding: 'utf8' });

const base = run();
if (base.status !== 0) { console.error('baseline is not green; fix that first'); process.exit(1); }
console.log('baseline: green\n');

// Each mutant: [name, transform(src) -> mutated src | null]
// Returning null means the pattern this mutant needs is absent.
const MUTANTS = [
  ['rename the markup back to the bare class (the fork)',
   (s) => s.includes('class="cm-head"') ? s.replace('class="cm-head"', 'class="about-head"') : null],
  ['re-introduce the forked .about-head rule',
   (s) => s.includes('.about-body {') ? s.replace('.about-body {', '.about-head { padding: var(--head-top) 0 2rem; }\n\n\t.about-body {') : null],
  ['keep the forked title rule',
   (s) => s.includes('.about-body {') ? s.replace('.about-body {', '.about-head h1 { font-size: var(--head-h1); margin: 0; letter-spacing: -0.01em; }\n\n\t.about-body {') : null],
];

let killed = 0;
for (const [name, transform] of MUTANTS) {
  const before = readFileSync(about, 'utf8');
  const after = transform(before);
  if (after === null) { console.log(`SKIP  ${name}  (pattern absent)`); continue; }
  writeFileSync(about, after);
  const r = run();
  const ok = r.status !== 0;
  writeFileSync(about, before);
  console.log(`${ok ? 'KILL' : 'MISSED'}  ${name}`);
  if (ok) killed++;
}
console.log(`\n${killed}/${MUTANTS.length} mutants killed`);
process.exit(killed === MUTANTS.length ? 0 : 1);