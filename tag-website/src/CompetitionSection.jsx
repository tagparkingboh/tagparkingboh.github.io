import './CompetitionSection.css'

// Auto-hides at 5pm UK on 18 May 2026 (competition close).
// Drop the file (and the import in HomePage.jsx) once the promo is over.
const COMPETITION_CLOSES_AT = new Date('2026-05-18T17:00:00+01:00')

const INSTAGRAM_POST_URL = 'https://www.instagram.com/p/DYPiEs4NYsF/'
const FACEBOOK_POST_URL = 'https://www.facebook.com/reel/1531598338340082/'

function CompetitionSection() {
  if (new Date() >= COMPETITION_CLOSES_AT) {
    return null
  }

  return (
    <section className="competition-section" id="competition">
      <h2>Win 2 tickets</h2>
      <p className="competition-subtitle">
        AFC Bournemouth vs Manchester City — Tuesday 19th May, 7:30pm kick off
        at the Vitality Stadium, courtesy of Tag Parking.
      </p>

      <div className="competition-card">
        <div className="competition-images">
          <img
            src="/assets/competition-vs.png"
            alt="AFC Bournemouth versus Manchester City FC"
            className="competition-image"
            loading="lazy"
          />
          <img
            src="/assets/competition-win.png"
            alt="Win 2 tickets — AFC Bournemouth vs Manchester City"
            className="competition-image"
            loading="lazy"
          />
        </div>

        <div className="competition-body">
          <p className="competition-instructions">
            To enter on Instagram or Facebook:{' '}
            <strong>like, share, and comment</strong> on the post (tag your
            plus 1) and give us a follow. Winners contacted within the hour
            after entries close.
          </p>
          <p className="competition-closes">
            Entries close <strong>5pm Monday 18th May 2026</strong>.
          </p>

          <div className="competition-actions">
            <a
              href={INSTAGRAM_POST_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="competition-cta competition-cta-primary"
            >
              Enter on Instagram →
            </a>
            <a
              href={FACEBOOK_POST_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="competition-cta competition-cta-secondary"
            >
              Enter on Facebook →
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}

export default CompetitionSection
