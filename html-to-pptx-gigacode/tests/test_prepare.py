import importlib.util,json,tempfile,unittest,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare',ROOT/'.gigacode/skills/html-to-pptx/scripts/prepare.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.src=self.root/'input.html';self.out=self.root/'export.html'
 def tearDown(self):self.temp.cleanup()
 def run_doc(self,text):self.src.write_text(text,encoding='utf-8');return m.prepare(self.src,self.out)
 def test_demo(self):
  self.assertEqual(self.run_doc((ROOT/'examples/demo.html').read_text())['slides'],2)
  self.assertIn("connect-src",self.out.read_text())
 def test_no_slide(self):
  with self.assertRaises(m.PreparationError):self.run_doc('<p>Hi</p>')
 def test_external_image(self):
  with self.assertRaises(m.PreparationError):self.run_doc('<section class="slide"><img src="https://example.com/a.png"></section>')
 def test_path_escape(self):
  with self.assertRaises(m.PreparationError):self.run_doc('<section class="slide"><img src="../secret.png"></section>')
 def test_strip_scripts(self):
  r=self.run_doc('<section class="slide" onclick="evil()">Hello<script>SECRET_CODE()</script></section>')
  self.assertTrue(r['warnings']);self.assertNotIn('SECRET_CODE',self.out.read_text());self.assertNotIn('onclick=\\"evil',self.out.read_text())
 def test_css_local(self):
  (self.root/'css').mkdir();(self.root/'css/b.css').write_text('.slide{color:red}')
  (self.root/'css/a.css').write_text('@import "b.css"; .slide{background:url("../x.png")}')
  (self.root/'x.png').write_bytes(b'fake-for-bundling')
  self.run_doc('<link rel="stylesheet" href="css/a.css"><section class="slide">A</section>')
  self.assertIn('data:image/png;base64',self.out.read_text());self.assertIn('color:red',self.out.read_text())
 def test_cycle(self):
  (self.root/'a.css').write_text('@import "a.css";')
  with self.assertRaises(m.PreparationError):self.run_doc('<link rel="stylesheet" href="a.css"><section class="slide">A</section>')
 def test_no_overwrite(self):
  self.out.write_text('keep')
  with self.assertRaises(m.PreparationError):self.run_doc('<section class="slide">A</section>')
  self.assertEqual(self.out.read_text(),'keep')
 def test_srcset(self):
  with self.assertRaises(m.PreparationError):self.run_doc('<section class="slide"><img srcset="x.png 1x"></section>')
 def test_base(self):
  with self.assertRaises(m.PreparationError):self.run_doc('<base href="https://example.com"><section class="slide">A</section>')
if __name__=='__main__':unittest.main()
