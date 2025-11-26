import { Link } from 'react-router-dom'
import './Legal.css'

function CookiePolicy() {
  return (
    <div className="legal-page">
      <nav className="legal-nav">
        <Link to="/" className="logo">
          <img src="/logo.svg" alt="TAG - Book it. Bag it. Tag it." className="logo-svg" />
        </Link>
      </nav>

      <div className="legal-container">
        <Link to="/" className="legal-back-link">
          ← Back to Home
        </Link>

        <h1>Cookie Policy</h1>
        <p className="legal-subtitle">Last Updated: November 2025</p>

        <div className="legal-content">
          <h2>1. What Are Cookies?</h2>
          <p>Cookies are small text files that are placed on your computer, smartphone, or other device when you visit our website. They are widely used to make websites work more efficiently and provide a better user experience. Cookies help us remember your preferences, understand how you use our site, and improve our services.</p>
          <p><strong>Quick Summary:</strong> Cookies help our website function properly and remember your preferences. You have full control over which cookies you accept through your browser settings or our cookie consent banner.</p>

          <h2>2. Types of Cookies We Use</h2>

          <h3>2.1 Essential Cookies (Always Active)</h3>
          <p>These cookies are strictly necessary for our website to function properly. They enable core functionality and security features. Without these cookies, services you have requested cannot be provided.</p>
          <p>Essential cookies enable:</p>
          <ul>
            <li>Secure login and authentication</li>
            <li>Booking system functionality</li>
            <li>Payment processing and checkout</li>
            <li>Session management and security</li>
            <li>Load balancing and performance</li>
            <li>Cookie consent preferences</li>
          </ul>
          <p><strong>Important:</strong> You cannot disable essential cookies as they are required for the website to work. Blocking these cookies may prevent you from making bookings or accessing certain features.</p>

          <h3>2.2 Performance Cookies (Optional)</h3>
          <p>These cookies collect anonymous information about how visitors use our website. They help us understand which pages are most popular, identify technical issues, and improve our website's performance.</p>
          <p>Performance cookies help us:</p>
          <ul>
            <li>Count visitor numbers and traffic sources</li>
            <li>Understand which pages are visited most often</li>
            <li>Measure how long visitors spend on each page</li>
            <li>Identify navigation patterns and user journeys</li>
            <li>Detect and fix technical errors</li>
            <li>Test different versions of pages to improve user experience</li>
          </ul>
          <p><strong>Examples:</strong> Google Analytics, Hotjar</p>

          <h3>2.3 Functional Cookies (Optional)</h3>
          <p>These cookies remember your preferences and choices to provide enhanced, personalised features. They improve your experience by remembering settings you've selected.</p>
          <p>Functional cookies remember:</p>
          <ul>
            <li>Your language preference</li>
            <li>Your region or location</li>
            <li>Previously entered booking information</li>
            <li>Display preferences (e.g., text size)</li>
            <li>Whether you've seen certain messages or notifications</li>
          </ul>

          <h3>2.4 Marketing Cookies (Optional)</h3>
          <p>These cookies track your browsing activity across websites to deliver relevant advertising. They help us show you ads that are more relevant to your interests and measure the effectiveness of our advertising campaigns.</p>
          <p>Marketing cookies are used to:</p>
          <ul>
            <li>Track visits to our website from advertising campaigns</li>
            <li>Track visits to other websites after leaving ours</li>
            <li>Deliver targeted advertising based on your interests</li>
            <li>Measure advertising campaign effectiveness</li>
            <li>Limit the number of times you see an advertisement</li>
            <li>Build a profile of your interests</li>
          </ul>
          <p><strong>Examples:</strong> Google Ads, Facebook Pixel, Meta Pixel, LinkedIn Insight Tag</p>

          <h2>3. How to Manage Cookies</h2>

          <h3>3.1 Cookie Consent Banner</h3>
          <p>When you first visit our website, you will see a cookie consent banner with the following options:</p>
          <ul>
            <li><strong>Accept All Cookies:</strong> Allows all cookies including marketing and performance cookies</li>
            <li><strong>Reject Optional Cookies:</strong> Only essential cookies will be used</li>
            <li><strong>Customise Settings:</strong> Choose which types of cookies you want to accept</li>
          </ul>
          <p>You can change your cookie preferences at any time by clicking the "Cookie Settings" link in our website footer.</p>

          <h3>3.2 Browser Settings</h3>
          <p>You can also control cookies through your web browser settings. Most browsers allow you to:</p>
          <ul>
            <li>View and delete cookies</li>
            <li>Block all cookies</li>
            <li>Block third-party cookies only</li>
            <li>Clear cookies when you close your browser</li>
            <li>Receive notifications when cookies are set</li>
          </ul>
          <p><strong>How to manage cookies in different browsers:</strong></p>
          <ul>
            <li><strong>Google Chrome:</strong> Settings → Privacy and security → Cookies and other site data</li>
            <li><strong>Mozilla Firefox:</strong> Options → Privacy & Security → Cookies and Site Data</li>
            <li><strong>Safari:</strong> Preferences → Privacy → Cookies and website data</li>
            <li><strong>Microsoft Edge:</strong> Settings → Cookies and site permissions → Cookies and site data</li>
          </ul>

          <h3>3.3 Third-Party Opt-Out Tools</h3>
          <p>You can opt out of specific third-party cookies using these tools:</p>
          <ul>
            <li><strong>Google Analytics:</strong> Google Analytics Opt-out Browser Add-on</li>
            <li><strong>Google Ads:</strong> Google Ads Settings</li>
            <li><strong>Facebook:</strong> Facebook Ad Preferences</li>
            <li><strong>Network Advertising Initiative:</strong> NAI Opt-Out Tool</li>
            <li><strong>Digital Advertising Alliance:</strong> DAA Opt-Out Tool</li>
          </ul>

          <h2>4. Impact of Disabling Cookies</h2>

          <h3>4.1 Disabling Essential Cookies</h3>
          <p>If you disable essential cookies, you will not be able to:</p>
          <ul>
            <li>Make bookings on our website</li>
            <li>Complete payment transactions</li>
            <li>Access secure areas of the website</li>
            <li>Use the full functionality of our booking system</li>
          </ul>
          <p><strong>Warning:</strong> Blocking essential cookies will significantly impact your ability to use our website and services.</p>

          <h3>4.2 Disabling Optional Cookies</h3>
          <p>If you disable performance, functional, or marketing cookies:</p>
          <ul>
            <li>The website will still function normally for bookings</li>
            <li>You may see less relevant advertising</li>
            <li>We cannot track website performance or user behaviour</li>
            <li>Some personalised features may not work</li>
            <li>You may need to re-enter preferences each visit</li>
          </ul>

          <h2>5. First-Party vs Third-Party Cookies</h2>

          <h3>5.1 First-Party Cookies</h3>
          <p>First-party cookies are set directly by Tag Parking Ltd when you visit our website. We use these cookies to:</p>
          <ul>
            <li>Manage your booking session</li>
            <li>Remember your preferences</li>
            <li>Improve website functionality</li>
            <li>Analyse how you use our site</li>
          </ul>

          <h3>5.2 Third-Party Cookies</h3>
          <p>Third-party cookies are set by external services we use on our website, such as:</p>
          <ul>
            <li>Google Analytics (website analytics)</li>
            <li>Google Ads (advertising)</li>
            <li>Facebook Pixel (advertising and analytics)</li>
            <li>Payment processors (secure transactions)</li>
          </ul>
          <p>These third parties have their own privacy policies and cookie policies. We recommend reviewing their policies to understand how they use cookies.</p>

          <h2>6. Cookie Lifespan</h2>

          <h3>6.1 Session Cookies</h3>
          <p>Session cookies are temporary and are deleted when you close your browser. They are essential for website functionality during your visit.</p>

          <h3>6.2 Persistent Cookies</h3>
          <p>Persistent cookies remain on your device for a set period (from 24 hours to 2 years) or until you manually delete them. They remember your preferences across multiple visits.</p>

          <h2>7. Updates to This Cookie Policy</h2>
          <p>We may update this Cookie Policy from time to time to reflect:</p>
          <ul>
            <li>Changes in the cookies we use</li>
            <li>Changes in technology</li>
            <li>Changes in legal or regulatory requirements</li>
            <li>Improvements to our website and services</li>
          </ul>
          <p>When we make changes, we will update the "Last Updated" date at the top of this policy and post the revised policy on our website.</p>

          <h2>8. More Information</h2>
          <p>For more information about cookies and how they work, visit:</p>
          <ul>
            <li><strong>All About Cookies:</strong> www.allaboutcookies.org</li>
            <li><strong>ICO Cookie Guidance:</strong> ico.org.uk/for-organisations/guide-to-pecr/cookies-and-similar-technologies/</li>
            <li><strong>Your Online Choices:</strong> www.youronlinechoices.com</li>
          </ul>

          <h2>9. Contact Us</h2>
          <p>If you have any questions about our use of cookies or this Cookie Policy, please contact us:</p>
          <p><strong>Tag Parking Ltd</strong></p>
          <p><strong>Address:</strong> 5 Ivegate, Yeadon, Leeds, England, LS19 7RE</p>
          <p><strong>Phone:</strong> 07739106145</p>
          <p><strong>Email:</strong> info@tagparking.co.uk</p>

          <div className="legal-footer">
            <p>© 2025 Tag Parking Ltd. All rights reserved.</p>
            <p>Registered in England and Wales</p>
            <p>Registered Address: 5 Ivegate, Yeadon, Leeds, England, LS19 7RE</p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default CookiePolicy
