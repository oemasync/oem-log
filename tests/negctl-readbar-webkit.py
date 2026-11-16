# NEGATIVE CONTROL for tests/verify-readbar-webkit.py.
#
# A probe that has never failed is a probe nobody has shown can work.
# This one plants the WRONG shape in the vendored runtime and requires
# the probe's tracking assertion to go red on it:
#
#   The scroll listener bound to the SCROLLER ELEMENT instead of window.
#   In WebKit the scroll event targets the document, not
#   documentElement, so that listener never fires, and the bar sits at
#   0 for the whole read while looking perfectly correct at the top of
#   the page - and while the runtime's own writes (--cm-readbar,
#   aria-valuenow) are still made exactly once at bind time. A probe
#   that only reads the DOM at the top of the article cannot tell the
#   two apart; only the scroll-and-read can.
#
# The mutant lives in the BUILT page, so the control rebuilds dev-blog
# twice (mutated, then restored) and serves both through the LAN
# preview the main probe uses. The restore is byte-verified against an
# in-memory snapshot, and the run ends by asserting the tree is exactly
# as it was when the run started.
import hashlib
import os
import subprocess
import sys

from playwright.sync_api import sync_playwright

# Probes self-rescue a dead PLAYWRIGHT_BROWSERS_PATH: the host export may
# point at a cache that holds no webkit build, and playwright then refuses
# to launch. Delete the var only when the named cache lacks a webkit build
# - an unconditional delete would discard a restored cache.
_pw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if _pw and (not os.path.isdir(_pw) or not any(
        d.startswith("webkit-") for d in os.listdir(_pw)
        if os.path.isdir(os.path.join(_pw, d)))):
    del os.environ["PLAYWRIGHT_BROWSERS_PATH"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("BLOG_URL", "http://192.168.1.68:4322")
POST = "/blog/getting-tracking-data-from-fedex-consistently/"

RUNTIME = os.path.join(ROOT, "src/js/cli-mono.js")
OLD = "window.addEventListener('scroll', paint, { passive: true });"
NEW = "box.addEventListener('scroll', paint, { passive: true });"


def md5(path):
	with open(path, "rb") as f:
		return hashlib.md5(f.read()).hexdigest()


def build():
	r = subprocess.run(["npm", "run", "build"], cwd=ROOT,
					 capture_output=True, text=True, timeout=300)
	if r.returncode != 0:
		print(r.stdout[-2000:], r.stderr[-2000:])
		raise SystemExit("build failed")


def wait_mark(pg, timeout=15000):
    # wait_for_function lies on the first call after a 'commit' navigation
    # in this engine; poll evaluate instead.
    import time
    t0 = time.time()
    while time.time() - t0 < timeout / 1000:
        if pg.evaluate(
                "() => document.documentElement.classList.contains('cm-js') "
                "|| !!window.cliMono"):
            return
        pg.wait_for_timeout(200)
    raise RuntimeError("runtime mark never appeared")

def scroll_and_read(pg):
    pg.goto(BASE + POST, wait_until="commit")
    wait_mark(pg)
    pg.wait_for_timeout(120)
    max_ = pg.evaluate(
        "() => document.scrollingElement.scrollHeight - "
        "document.scrollingElement.clientHeight")
    assert max_ > 200, f"fixture does not scroll ({max_:.0f}px); " \
        "the control is vacuous"
    pg.evaluate("y => window.scrollTo(0, y)", max_ * 0.5)
    pg.wait_for_timeout(400)
    return pg.evaluate("""() => {
        const bar = document.querySelector('.cm-readbar');
        return {
            val: bar.style.getPropertyValue('--cm-readbar'),
            aria: bar.getAttribute('aria-valuenow'),
            y: window.scrollY,
        };
    }""")


def main():
	before_status = subprocess.run(
		["git", "status", "--porcelain"], cwd=ROOT,
		capture_output=True, text=True).stdout
	src = open(RUNTIME).read()
	assert src.count(OLD) == 1, f"anchor matches {src.count(OLD)}; abort"
	start_md5 = md5(RUNTIME)

	# ---- plant the wrong shape, rebuild, require the probe to fail ----
	open(RUNTIME, "w").write(src.replace(OLD, NEW, 1))
	assert md5(RUNTIME) != start_md5, "mutation write failed"
	build()
	with sync_playwright() as p:
		b = p.webkit.launch()
		pg = b.new_page(viewport={"width": 402, "height": 874},
						device_scale_factor=2)
		mut = scroll_and_read(pg)
		pg.close()
		b.close()
	print(f"mutated build: after a real 50% scroll the bar reads "
		  f"--cm-readbar={mut['val']} aria={mut['aria']} (y={mut['y']:.0f})")
	if float(mut["val"].rstrip("%")) >= 10:
		print("!! the element-bound listener DID fire in WebKit; "
			  "the planted defect is not the defect - abort")
		open(RUNTIME, "w").write(src)
		build()
		sys.exit(1)
	print("OK - the wrong shape is dead in this engine, exactly as the")
	print("    probe's tracking assertion must see it (the probe would")
	print("    have failed: it requires ~50, the mutant reads 0)")

	# ---- restore, rebuild, require the probe to pass again ----
	open(RUNTIME, "w").write(src)
	assert md5(RUNTIME) == start_md5, "restore failed"
	build()
	with sync_playwright() as p:
		b = p.webkit.launch()
		pg = b.new_page(viewport={"width": 402, "height": 874},
						device_scale_factor=2)
		clean = scroll_and_read(pg)
		pg.close()
		b.close()
	print(f"restored build: after the same scroll the bar reads "
		  f"--cm-readbar={clean['val']} aria={clean['aria']}")
	if float(clean["val"].rstrip("%")) < 40:
		print("!! the restored build does not track; the tree is not "
			  "back to green - abort")
		sys.exit(1)

	after_status = subprocess.run(
		["git", "status", "--porcelain"], cwd=ROOT,
		capture_output=True, text=True).stdout
	if after_status != before_status:
		print("!! git status moved during the run:\n"
			  f"before:\n{before_status}\nafter:\n{after_status}")
		sys.exit(1)
	print("OK - tree unchanged; control passes on both ends")


if __name__ == "__main__":
	main()
