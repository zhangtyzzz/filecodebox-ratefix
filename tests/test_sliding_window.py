import asyncio,datetime,importlib.util,os,unittest
from unittest.mock import patch
from starlette.requests import Request
from core.settings import settings
path=os.environ.get('RATE_DEPENDENCIES','/app/apps/base/dependencies.py')
spec=importlib.util.spec_from_file_location('ratefix_test_module',path);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
class Clock:
 value=0
 def __call__(self):return self.value
clock=Clock()
class FakeDatetime(datetime.datetime):
 @classmethod
 def now(cls,tz=None):return datetime.datetime(2026,10,25)+datetime.timedelta(seconds=clock.value)
class RateTests(unittest.TestCase):
 def setUp(self):
  clock.value=0;self.p=patch.object(d.time,'monotonic',clock);self.p.start();self.dp=patch.object(d,'datetime',FakeDatetime,create=True);self.dp.start();self.l=d.IPRateLimit(3,1)
 def tearDown(self):self.p.stop();self.dp.stop()
 def add(self,t,ip='192.0.2.10'):
  clock.value=t;self.assertTrue(self.l.check_ip(ip));self.l.add_ip(ip)
 def test_sparse_events_do_not_accumulate(self):
  for t in [0,70,140,141]:self.add(t)
 def test_only_recent_three_count(self):
  for t in [0,40,61,62]:self.add(t)
  clock.value=63;self.assertFalse(self.l.check_ip('192.0.2.10'))
 def test_strict_burst_and_independent_ip(self):
  for t in [0,1,2]:self.add(t)
  self.assertFalse(self.l.check_ip('192.0.2.10'));self.assertTrue(self.l.check_ip('192.0.2.11'))
 def test_boundary_expires_oldest_without_erasing_others(self):
  for t in [0,10,20]:self.add(t)
  clock.value=59;self.assertFalse(self.l.check_ip('192.0.2.10'))
  self.add(60);self.assertFalse(self.l.check_ip('192.0.2.10'))
 def test_cleanup_prunes_without_waiting_for_threshold(self):
  self.add(0);self.add(1,ip='192.0.2.11');clock.value=61;asyncio.run(self.l.remove_expired_ip());self.assertFalse(self.l.ips)
class ProxyTests(unittest.TestCase):
 def setUp(self):self.old=settings.user_config;settings.user_config={'trusted_proxies':['172.18.0.5/32']}
 def tearDown(self):settings.user_config=self.old
 def req(self,peer,xff=None,real=None):
  h=[]
  if xff is not None:h.append((b'x-forwarded-for',xff.encode()))
  if real is not None:h.append((b'x-real-ip',real.encode()))
  return Request({'type':'http','client':(peer,12345),'headers':h,'method':'GET','path':'/'})
 def test_known_proxy_uses_nearest_verified_client(self):
  self.assertEqual(d.get_client_ip(self.req('172.18.0.5','203.0.113.66, 198.51.100.9','198.51.100.9')),'198.51.100.9')
 def test_untrusted_client_cannot_spoof_forwarded_headers(self):
  self.assertEqual(d.get_client_ip(self.req('198.51.100.9','203.0.113.66','203.0.113.66')),'198.51.100.9')
 def test_ipv6_client_preserved(self):self.assertEqual(d.get_client_ip(self.req('172.18.0.5','2001:db8::123')),'2001:db8::123')
 def test_bad_forwarded_address_fails_closed(self):self.assertEqual(d.get_client_ip(self.req('172.18.0.5','invalid-ip')),'172.18.0.5')
if __name__=='__main__':unittest.main()
