document.addEventListener('DOMContentLoaded', () => {
    // Scroll observer for animations
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.15
    };

    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Elements to animate
    const animElements = document.querySelectorAll('.fade-in-up, .slide-in-bottom');
    animElements.forEach(el => observer.observe(el));

    // Navbar background on scroll
    const navbar = document.querySelector('.navbar');
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.style.padding = '0.5rem 0';
            navbar.style.boxShadow = '0 4px 6px -1px rgba(0, 0, 0, 0.05)';
        } else {
            navbar.style.padding = '0';
            navbar.style.boxShadow = 'none';
        }
    });

    // Mobile menu toggle (basic)
    const menuToggle = document.querySelector('.menu-toggle');
    const navLinks = document.querySelector('.nav-links');
    
    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            if(targetId === '#') return;
            const targetEl = document.querySelector(targetId);
            if(targetEl) {
                targetEl.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });
});

// Modal Logic
function openCaseModal() {
    const modal = document.getElementById('logistics-modal');
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden'; // Prevent background scrolling
    }
}

function closeCaseModal() {
    const modal = document.getElementById('logistics-modal');
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close modal when clicking outside of it
window.addEventListener('click', (event) => {
    const modal = document.getElementById('logistics-modal');
    if (event.target === modal) {
        closeCaseModal();
    }
});
// Close modal on Escape key
window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        closeCaseModal();
    }
});
