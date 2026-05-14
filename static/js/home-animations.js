/* Home Page Animations & Interactions */
(function(){
  "use strict";

  // ── Scroll Reveal ──
  function initReveal(){
    var els=document.querySelectorAll('.sc-reveal');
    if(!els.length) return;
    var observer=new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if(entry.isIntersecting){
          var delay=parseInt(entry.target.getAttribute('data-delay')||'0',10);
          setTimeout(function(){entry.target.classList.add('visible');},delay);
          observer.unobserve(entry.target);
        }
      });
    },{threshold:0.12,rootMargin:'0px 0px -40px 0px'});
    els.forEach(function(el){observer.observe(el);});
  }

  // ── Confidence Bar Animation ──
  function initConfidenceBar(){
    var fill=document.querySelector('.hero-confidence-fill');
    if(!fill) return;
    setTimeout(function(){
      fill.style.width=fill.getAttribute('data-target')+'%';
    },800);
  }

  // ── Mobile Menu Toggle ──
  function initMobileMenu(){
    var toggle=document.getElementById('sc-mobile-toggle');
    var menu=document.getElementById('sc-mobile-menu');
    if(!toggle||!menu) return;
    toggle.addEventListener('click',function(){
      toggle.classList.toggle('open');
      menu.classList.toggle('open');
    });
  }

  // ── Navbar Scroll Effect ──
  function initNavScroll(){
    var nav=document.getElementById('sc-navbar');
    if(!nav) return;
    var last=0;
    window.addEventListener('scroll',function(){
      var y=window.scrollY;
      if(y>80){
        nav.style.background='rgba(5,8,22,.95)';
        nav.style.borderBottomColor='rgba(255,255,255,.1)';
      }else{
        nav.style.background='rgba(5,8,22,.8)';
        nav.style.borderBottomColor='rgba(255,255,255,.08)';
      }
      last=y;
    },{passive:true});
  }

  // ── Init ──
  document.addEventListener('DOMContentLoaded',function(){
    initReveal();
    initConfidenceBar();
    initMobileMenu();
    initNavScroll();
  });
})();
