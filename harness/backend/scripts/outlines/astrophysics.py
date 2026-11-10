"""Astrophysics outline, in the shape ``scripts/course_pipeline.py`` expects.

Scope and sequence authored for the Luminfest Learning Harness (CC0). The sequence runs
from the measurement tools of the discipline, through the sky and Newtonian mechanics,
radiation and spectra, telescopes, binary stars and the HR diagram, stellar interiors and
evolution, compact objects, galaxies, cosmology, and closes with the solar system and
exoplanets.

Textbook anchors are OpenStax **Astronomy (1e)**, which reports CC BY 4.0 and is
text-eligible in ``app/ingest/policy.py``. The second edition ``astronomy-2e`` reports
CC BY-NC-SA and is a link-only reference: it is named in ``TEXTBOOK['link_only_note']``
and never used as an anchor.

Every page slug below was read from the publisher's own table of contents via
``scripts/probe_sections.py --book astronomy``.
"""

from __future__ import annotations

ID = 'astrophysics'
TITLE = 'Astrophysics'
SUBJECT = 'Astronomy'
SUBJECT_KIND = 'science'
EXPECTED_WEEKS = 36
COURSE_LINE = 'Astrophysics - Tools, Stars, Galaxies and the Universe'
DESCRIPTION = ('A quantitative introduction to astrophysics: astronomical measurement and the '
               'celestial sphere, gravitation and orbits, radiation and spectra, telescopes and '
               'detectors, binary stars and the HR diagram, stellar atmospheres and interiors, '
               'star formation and evolution, compact objects, the Milky Way and galaxies, '
               'cosmology, and the solar system with its exoplanets.')

TEXTBOOK = {
    'spine': 'OpenStax Astronomy (1e, CC BY 4.0)',
    'supplements': [],
    'link_only_note': ('OpenStax Astronomy 2e reports CC BY-NC-SA 4.0 and is carried as a '
                       'link-only study reference: never stored, quoted or used as an anchor.'),
}

UNITS = [
    # ---------------------------------------------------------------- 1
    {
        'unit': 'Astrophysical Tools & Measurement',
        'about': 'Fixes the units, angles, uncertainty language and graphing habits every later '
                 'model in the course is written in.',
        'sections': [
            ('astronomy', '1-4-numbers-in-astronomy'),
            ('astronomy', '1-7-the-universe-on-the-large-scale'),
            ('astronomy', '1-1-the-nature-of-astronomy'),
        ],
        'topics': [
            ('Units, Scale & Dimensional Reasoning', [
                ('SI Units and Astronomical Distance Scales',
                 'Every measurement reduces to the seven SI base units, and astronomy adds the '
                 'astronomical unit (1.496x10^11 m), the light-year (9.46x10^15 m) and the parsec '
                 '(3.086x10^16 m, or 3.26 ly).',
                 ['si units', 'parsec', 'light-year']),
                ('Dimensional Analysis of Physical Laws',
                 'An equation is dimensionally consistent only when both sides carry the same '
                 'base-unit powers, so a candidate such as L ~ M R^2/t^3 can be tested before any '
                 'data are taken, though consistency alone does not prove a law correct.',
                 ['dimensional analysis', 'units', 'scaling']),
            ]),
            ('Angular Measure', [
                ('Angular Size and the Small-Angle Relation',
                 "A body of diameter D at distance d subtends about D/d radians, so the Moon's "
                 '3 475 km at 384 000 km gives 0.52 degrees, and one angular size can mean a small '
                 'near object or a large distant one.',
                 ['angular size', 'small angle', 'distance']),
            ]),
            ('Significant Figures & Uncertainty', [
                ('Significant Figures and Propagated Uncertainty',
                 'A quoted value carries only the digits the instrument resolves, so 12.30 mag '
                 'claims 0.01 mag precision while 12.3 mag claims 0.1 mag, and averaging N '
                 'readings shrinks random error as 1/sqrt(N) while a systematic offset survives.',
                 ['significant figures', 'uncertainty', 'systematic error']),
            ]),
            ('Graphical Analysis & Curve Fitting', [
                ('Logarithmic Plots and Power-Law Fits',
                 'Plotting log y against log x turns y = k x^n into a straight line of slope n, '
                 'which is how a luminosity-mass exponent near 3.5 is read straight off the graph.',
                 ['log plot', 'power law', 'least squares']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 2
    {
        'unit': 'The Celestial Sphere, Coordinates & Time',
        'about': 'Gives the sky a geometry and a clock, so a position and a moment can be stated '
                 'unambiguously from any observing site.',
        'sections': [
            ('astronomy', '2-1-the-sky-above'),
            ('astronomy', '4-1-earth-and-sky'),
            ('astronomy', '4-3-keeping-time'),
            ('astronomy', '4-7-eclipses-of-the-sun-and-moon'),
        ],
        'topics': [
            ('Spherical Trigonometry on the Sky', [
                ('Great Circles and Spherical Angles',
                 'Two great circles cross at antipodal points and enclose an angle equal to the '
                 'dihedral angle of their planes, while a small circle such as a declination '
                 'parallel does not pass through the centre of the sphere.',
                 ['great circle', 'spherical angle', 'small circle']),
                ('The Spherical Law of Cosines',
                 'The spherical law of cosines, cos a = cos b cos c + sin b sin c cos A, converts '
                 'between horizon and equatorial coordinates once latitude, declination and hour '
                 'angle are known.',
                 ['spherical trigonometry', 'coordinate conversion', 'hour angle']),
            ]),
            ('The Celestial Sphere & Its Motions', [
                ('Diurnal Rotation and Circumpolar Stars',
                 'The sky turns once on the polar axis in a sidereal day, so a star of declination '
                 'd culminates at altitude 90 - |latitude - d| degrees and never sets when '
                 'd > 90 - latitude.',
                 ['diurnal motion', 'culmination', 'circumpolar']),
            ]),
            ('Celestial Coordinate Systems & Transforms', [
                ('Horizon, Equatorial and Ecliptic Frames',
                 "Each frame is tied to a different reference, the observer's zenith, Earth's "
                 "equator or the ecliptic, so a star's altitude changes hourly while its right "
                 'ascension and declination stay nearly fixed.',
                 ['right ascension', 'declination', 'ecliptic coordinates']),
            ]),
            ('Time Systems, Precession, Proper Motion & Parallax', [
                ('Sidereal and Solar Time',
                 'A sidereal day lasts 23 h 56 m 4 s of solar time because Earth must turn about '
                 'one degree extra to bring the Sun back to the meridian, and that daily shortfall '
                 'accumulates into the seasonal drift of the night sky.',
                 ['sidereal time', 'solar time', 'meridian']),
                ('Parallax, Proper Motion and Precession',
                 'A parallax of p arcseconds puts a star at d = 1/p parsecs, proper motion is the '
                 'transverse velocity divided by distance, and precession carries the equinoxes '
                 'round the ecliptic once in about 26 000 years.',
                 ['parallax', 'proper motion', 'precession']),
            ]),
            ('Sky Phenomena: Seasons, Rise/Set & Eclipses', [
                ('Seasons, Rise and Set, and Eclipse Geometry',
                 "Seasons follow from the 23.4 degree tilt of Earth's axis rather than its varying "
                 'distance from the Sun, and a solar eclipse needs a new moon within about 18 '
                 'degrees of a lunar node.',
                 ['seasons', 'obliquity', 'eclipse']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 3
    {
        'unit': 'Gravity, Orbits & Celestial Mechanics',
        'about': "Turns gravity into the working machinery of orbits, from Kepler's ellipses to "
                 'tides and three-body geometry.',
        'sections': [
            ('astronomy', '3-1-the-laws-of-planetary-motion'),
            ('astronomy', '3-3-newtons-universal-law-of-gravitation'),
            ('astronomy', '3-4-orbits-in-the-solar-system'),
            ('astronomy', '3-6-gravity-with-more-than-two-bodies'),
        ],
        'topics': [
            ('Newtonian Gravity & Gravitational Energy', [
                ('The Inverse-Square Law of Gravitation',
                 'Two masses attract with F = G M m / r^2, so doubling the separation quarters the '
                 "force and a satellite at twice Earth's radius weighs a quarter of what it does "
                 'on the surface.',
                 ['universal gravitation', 'inverse square', 'newton']),
                ('Gravitational Potential Energy and Escape Speed',
                 'With U = -G M m / r measured from infinity, a body escapes when its kinetic '
                 'energy balances the well, giving v_esc = sqrt(2GM/r), which is 11.2 km/s at '
                 "Earth's surface.",
                 ['potential energy', 'escape velocity', 'binding energy']),
            ]),
            ("Kepler's Laws & the Geometry of the Ellipse", [
                ("Kepler's Laws and Orbital Geometry",
                 'Orbits are ellipses with the primary at a focus, the radius vector sweeps equal '
                 'areas in equal times, and P^2 = a^3 holds when P is in years and a in '
                 'astronomical units.',
                 ['kepler laws', 'ellipse', 'orbital period']),
            ]),
            ('Orbital Energy, Angular Momentum & Vis-Viva', [
                ('The Vis-Viva Equation and Orbital Energy',
                 'The vis-viva equation v^2 = GM(2/r - 1/a) gives the speed anywhere on an orbit, '
                 'and the sign of the specific energy -GM/2a separates bound, parabolic and '
                 'hyperbolic paths.',
                 ['vis-viva', 'orbital energy', 'eccentricity']),
                ('Conservation of Angular Momentum',
                 'Specific angular momentum h = r v cos(phi) is constant because gravity is a '
                 'central force, which is why a comet is fastest at perihelion and why dA/dt = h/2 '
                 'never changes.',
                 ['angular momentum', 'areal velocity', 'perihelion']),
            ]),
            ('The Two-Body Problem, Barycentre & Reduced Mass', [
                ('Barycentre and Reduced Mass',
                 'Two bodies circle their common centre of mass with m1 r1 = m2 r2, and the '
                 'relative motion is one body of reduced mass m1 m2/(m1 + m2) orbiting the total '
                 'mass, so a star with a planet wobbles by only m_p/M_star of the separation.',
                 ['barycentre', 'reduced mass', 'two-body problem']),
            ]),
            ('Tides, the Roche Limit & Lagrange Points', [
                ('Tidal Forces, the Roche Limit and Lagrange Points',
                 'Tidal acceleration falls as 1/r^3, a fluid satellite is disrupted inside the '
                 'Roche limit at about 2.44 R (rho_M/rho_m)^(1/3), and the five Lagrange points are '
                 'where gravity and rotation balance in the co-rotating frame.',
                 ['tides', 'roche limit', 'lagrange points']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 4
    {
        'unit': 'Radiation, Light & Magnitudes',
        'about': 'Converts light into numbers, so a brightness and a colour become a luminosity, a '
                 'temperature and a distance.',
        'sections': [
            ('astronomy', '5-1-the-behavior-of-light'),
            ('astronomy', '5-2-the-electromagnetic-spectrum'),
            ('astronomy', '17-1-the-brightness-of-stars'),
            ('astronomy', '17-2-colors-of-stars'),
        ],
        'topics': [
            ('Light & the Electromagnetic Spectrum', [
                ('Wavelength, Frequency and the Spectrum',
                 'All electromagnetic radiation obeys c = lambda nu, so the 21 cm hydrogen line '
                 'sits at 1 420 MHz while a 1 m radio wave sits at 300 MHz, and the spectrum spans '
                 'more than twenty orders of magnitude in frequency.',
                 ['wavelength', 'frequency', 'electromagnetic spectrum']),
            ]),
            ('Blackbody Radiation', [
                ("Wien's Law and the Peak Wavelength",
                 "A blackbody peaks at lambda_max = 2.898x10^-3 m K divided by T, so the Sun's "
                 '5 800 K photosphere peaks near 500 nm and a 300 K planet peaks in the thermal '
                 'infrared near 10 microns.',
                 ['wien law', 'blackbody', 'peak wavelength']),
                ('The Stefan-Boltzmann Law',
                 'A blackbody radiates F = sigma T^4 per unit area, so doubling T multiplies the '
                 "output sixteenfold and a star's luminosity is L = 4 pi R^2 sigma T^4.",
                 ['stefan-boltzmann', 'luminosity', 'effective temperature']),
            ]),
            ('Flux, Luminosity & the Inverse-Square Law', [
                ('Flux, Luminosity and the Inverse-Square Law',
                 'Flux falls as F = L/(4 pi d^2), so a star ten times farther away is a hundred '
                 'times fainter, and a measured flux with a known distance yields the luminosity.',
                 ['flux', 'luminosity', 'inverse square']),
            ]),
            ('The Magnitude Scale', [
                ('The Pogson Magnitude Relation',
                 'Five magnitudes correspond to a flux ratio of exactly 100, so m1 - m2 = '
                 '-2.5 log10(F1/F2) and one magnitude is a factor of 2.512 in flux.',
                 ['magnitude', 'pogson', 'flux ratio']),
                ('Absolute Magnitude and the Distance Modulus',
                 'Apparent and absolute magnitude differ by m - M = 5 log10(d) - 5 with d in '
                 'parsecs, so a star of absolute magnitude 0 placed at 100 pc has m = 5.',
                 ['distance modulus', 'absolute magnitude', 'apparent magnitude']),
            ]),
            ('Color Index, Temperature & Bolometric Magnitude', [
                ('Colour Index and Bolometric Correction',
                 'The difference of two band magnitudes is a temperature proxy, B - V near 0.65 '
                 'for the Sun and negative for a hot B star, and the bolometric correction turns a '
                 'band magnitude into total flux, mattering most at both temperature extremes.',
                 ['color index', 'bolometric correction', 'temperature']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 5
    {
        'unit': 'Light-Matter Interaction & Spectra',
        'about': 'Explains why a spectrum carries temperature, composition, density and motion, '
                 'which is the information base of all observational astrophysics.',
        'sections': [
            ('astronomy', '5-3-spectroscopy-in-astronomy'),
            ('astronomy', '5-4-the-structure-of-the-atom'),
            ('astronomy', '5-5-formation-of-spectral-lines'),
            ('astronomy', '5-6-the-doppler-effect'),
        ],
        'topics': [
            ('Atomic Structure & the Bohr Model', [
                ('Quantised Energy Levels and Ionisation',
                 'A hydrogen electron occupies levels E_n = -13.6 eV / n^2, so 13.6 eV ionises the '
                 'ground state and the n = 2 level lies 3.4 eV below the continuum.',
                 ['bohr model', 'energy levels', 'ionisation']),
                ('The Rydberg Formula and Spectral Series',
                 'Transitions obey 1/lambda = R(1/n_f^2 - 1/n_i^2) with R = 1.097x10^7 m^-1, '
                 'placing the Balmer lines at 656, 486 and 434 nm and the Lyman series in the '
                 'ultraviolet.',
                 ['rydberg formula', 'balmer series', 'spectral lines']),
            ]),
            ("Kirchhoff's Laws & Spectrum Types", [
                ("Kirchhoff's Three Spectral Laws",
                 'A hot dense body emits a continuum, a hot low-density gas emits bright lines at '
                 'its own wavelengths, and a cooler gas in front of a continuum removes those same '
                 'wavelengths as absorption lines.',
                 ['kirchhoff laws', 'emission lines', 'absorption lines']),
            ]),
            ('The Doppler Shift & Radial Velocity', [
                ('Doppler Shift and Radial Velocity',
                 'For speeds well below c the shift is delta lambda/lambda = v_r/c, so a line at '
                 '500 nm displaced by 0.05 nm means 30 km/s, and only the line-of-sight component '
                 'can be measured this way.',
                 ['doppler shift', 'radial velocity', 'redshift']),
            ]),
            ('Spectral Line Formation', [
                ('Equivalent Width and the Curve of Growth',
                 'Line strength grows with the absorbing column in three regimes, linear in N, '
                 'roughly as sqrt(ln N) in the Doppler core and as sqrt(N) on the damping wings, so '
                 'equivalent width alone gives no abundance without the regime.',
                 ['equivalent width', 'curve of growth', 'saturation']),
            ]),
            ('Spectral Line Broadening', [
                ('Thermal and Pressure Broadening',
                 'Thermal motion widens a line by delta lambda/lambda = sqrt(2kT/m)/c, about '
                 '4x10^-5 for hydrogen at 10 000 K, while collisions thicken the damping wings in '
                 'proportion to density.',
                 ['doppler broadening', 'pressure broadening', 'line width']),
                ('Rotational and Macroturbulent Broadening',
                 'Rotation adds a profile whose full width is twice the projected equatorial speed, '
                 'which is why a fast rotator shows broad shallow lines and a slow rotator narrow '
                 'deep ones.',
                 ['rotation', 'line profile', 'projected velocity']),
            ]),
            ('Excitation & Ionization Populations', [
                ('The Boltzmann and Saha Equations',
                 'The Boltzmann equation sets the level populations at (g2/g1) exp(-dE/kT) and the '
                 'Saha equation sets the ionisation balance, which is why a cool star shows neutral '
                 'lines and a hot star of the same element shows ionised ones.',
                 ['boltzmann equation', 'saha equation', 'ionisation balance']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 6
    {
        'unit': 'Telescopes, Detectors & Multi-wavelength Astronomy',
        'about': 'Turns the theory of light into practice: what an aperture can collect, resolve '
                 'and record, and where the atmosphere stops it.',
        'sections': [
            ('astronomy', '6-1-telescopes'),
            ('astronomy', '6-3-visible-light-detectors-and-instruments'),
            ('astronomy', '6-4-radio-telescopes'),
            ('astronomy', '6-5-observations-outside-earths-atmosphere'),
        ],
        'topics': [
            ('Geometric Optics of Telescopes', [
                ('Focal Length, Magnification and Focal Ratio',
                 'Angular magnification is f_objective/f_eye, and the focal ratio f/D fixes both '
                 'the plate scale and the light concentration, so a 0.2 m f/10 telescope has a 2 m '
                 'focal length.',
                 ['focal length', 'magnification', 'focal ratio']),
            ]),
            ('Light-Gathering Power & Limiting Magnitude', [
                ('Collecting Area and Limiting Magnitude',
                 'Collecting area grows as D^2, so a 0.2 m telescope gathers about 800 times the '
                 'light of a 7 mm dark-adapted pupil, worth roughly 7 magnitudes of extra reach.',
                 ['aperture', 'limiting magnitude', 'light grasp']),
            ]),
            ('Angular Resolution, Seeing & Interferometry', [
                ('The Diffraction Limit',
                 'A circular aperture resolves two points only when they are separated by more '
                 'than 1.22 lambda/D radians, so a 0.1 m telescope at 500 nm is limited to about '
                 '1.3 arcseconds.',
                 ['diffraction limit', 'rayleigh criterion', 'resolution']),
                ('Seeing, Adaptive Optics and Interferometry',
                 'Atmospheric seeing near 1 arcsecond usually sets the real ground-based '
                 'resolution, and interferometry beats both limits by combining apertures across a '
                 'baseline B to reach roughly lambda/B.',
                 ['seeing', 'adaptive optics', 'interferometry']),
            ]),
            ('Telescope Designs & Aberrations', [
                ('Refracting and Reflecting Telescope Designs',
                 'Refractors suffer chromatic aberration and a size limit set by sagging glass, so '
                 'every large telescope is a reflector, in Newtonian, Cassegrain or Ritchey-Chretien '
                 'form according to the field and focal ratio required.',
                 ['refractor', 'reflector', 'cassegrain']),
            ]),
            ('Detectors & Observational Techniques', [
                ('Detectors, Integration Time and Signal-to-Noise',
                 'A CCD accumulates signal linearly while read noise and sky background add in '
                 'quadrature, so signal-to-noise grows as sqrt(t) when background-limited but only '
                 'as t when read-noise-limited.',
                 ['ccd', 'integration time', 'signal-to-noise']),
            ]),
            ('Atmospheric Windows & Multi-wavelength Astronomy', [
                ('Atmospheric Windows and Space Observatories',
                 'The atmosphere passes visible light and part of the radio band but absorbs '
                 'ultraviolet, X-rays and most infrared, so those bands need balloons, rockets or '
                 'space telescopes above most of the absorbing column.',
                 ['atmospheric windows', 'space telescope', 'multiwavelength']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 7
    {
        'unit': 'Binary Stars & Stellar Parameters',
        'about': 'Shows that almost every stellar quantity worth knowing, mass first of all, comes '
                 'from a star that orbits another one.',
        'sections': [
            ('astronomy', '18-2-measuring-stellar-masses'),
            ('astronomy', '17-4-using-spectra-to-measure-stellar-radius-composition-and-motion'),
            ('astronomy', '18-3-diameters-of-stars'),
        ],
        'topics': [
            ('Classifying Binary Systems', [
                ('Four Ways to Detect a Binary',
                 'A binary is classed by how it is found, resolved visually, by periodic line '
                 'splitting, by eclipses in the light curve or by the wobble of the primary, and '
                 'each class yields a different mix of orbital parameters.',
                 ['binary stars', 'light curve', 'detection methods']),
            ]),
            ('Stellar Masses from Visual Binaries', [
                ("Total Mass from Kepler's Third Law",
                 'For a visual binary the relative orbit gives a in astronomical units and P in '
                 'years, so the total mass follows from M1 + M2 = a^3/P^2 in solar masses.',
                 ['kepler third law', 'total mass', 'visual binary']),
                ('Individual Masses from the Barycentre',
                 'The barycentre divides the orbit in the ratio of the masses, so the measured '
                 'semi-major axes give M1/M2 = a2/a1 and, with the sum, each mass separately.',
                 ['mass ratio', 'barycentre', 'individual masses']),
            ]),
            ('Spectroscopic Binaries & the Mass Function', [
                ('The Mass Function of a Single-Lined Binary',
                 'A single-lined spectroscopic binary yields only the mass function '
                 '(M2 sin i)^3/(M1 + M2)^2 = P K1^3/(2 pi G), so the companion mass stays a lower '
                 'limit until the inclination is known.',
                 ['mass function', 'spectroscopic binary', 'inclination']),
            ]),
            ('Eclipsing Binaries: Radii & Temperature Ratios', [
                ('Radii from Eclipse Durations and Velocities',
                 'Eclipse durations divided by the projected orbital speed give the stellar radii '
                 'directly, because ingress lasts exactly the time to cross one stellar diameter.',
                 ['eclipsing binary', 'stellar radius', 'light curve']),
                ('Temperature Ratio from Eclipse Depths',
                 'The relative depths of the primary and secondary minima give the '
                 'surface-brightness ratio, so the temperature ratio follows from the fourth root '
                 'of the flux ratio in the same bandpass.',
                 ['eclipse depth', 'temperature ratio', 'surface brightness']),
            ]),
            ('The Mass-Luminosity Relation', [
                ('The Mass-Luminosity Relation',
                 'Main-sequence stars obey L/L_sun near (M/M_sun)^3.5, so a ten-solar-mass star is '
                 'about 3 000 times more luminous and, with only ten times the fuel, exhausts it '
                 'roughly 300 times sooner.',
                 ['mass-luminosity', 'main sequence', 'stellar lifetime']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 8
    {
        'unit': 'Stellar Classification & the HR Diagram',
        'about': 'Turns a catalogue of spectra into a two-dimensional map on which every star has '
                 'an address and a mass.',
        'sections': [
            ('astronomy', '17-3-the-spectra-of-stars-and-brown-dwarfs'),
            ('astronomy', '18-1-a-stellar-census'),
            ('astronomy', '18-4-the-h-r-diagram'),
            ('astronomy', '19-4-the-h-r-diagram-and-cosmic-distances'),
        ],
        'topics': [
            ('The OBAFGKM Spectral Sequence', [
                ('The Harvard Spectral Sequence',
                 'The sequence OBAFGKM runs from about 50 000 K down to 2 500 K with ten '
                 'subclasses each, so the Sun is a G2 star with T_eff near 5 800 K.',
                 ['spectral class', 'harvard sequence', 'temperature']),
            ]),
            ('MK Luminosity Classes', [
                ('The MK Luminosity Classes',
                 'The Yerkes system appends Ia, Ib, II, III, IV or V to the spectral type and '
                 'separates a supergiant from a dwarf of the same temperature, because a larger '
                 'radius means lower gravity and narrower pressure-broadened lines.',
                 ['luminosity class', 'surface gravity', 'mk system']),
            ]),
            ('The Hertzsprung-Russell Diagram', [
                ('Axes, Loci and the Main Sequence',
                 'The HR diagram plots luminosity against temperature, and stars gather on a main '
                 'sequence from hot and bright to cool and faint, with giants, supergiants and '
                 'white dwarfs lying off it.',
                 ['hr diagram', 'main sequence', 'luminosity']),
                ('Mass and Evolution Read off the HR Diagram',
                 'Position on the main sequence fixes mass, so its upper end holds short-lived '
                 'massive stars, and displacement off the sequence marks a post-main-sequence '
                 'stage.',
                 ['hr diagram', 'stellar mass', 'evolution']),
            ]),
            ('The Color-Magnitude Diagram', [
                ('Colour-Magnitude Diagrams of Star Clusters',
                 'Replacing temperature by colour index and luminosity by absolute magnitude gives '
                 "the observed colour-magnitude diagram, whose turnoff fixes a cluster's age and "
                 'whose red-giant branch tracks its metallicity.',
                 ['colour-magnitude', 'star cluster', 'turnoff']),
            ]),
            ('Spectroscopic Parallax', [
                ('Spectroscopic Parallax',
                 'Spectral type plus luminosity class fixes absolute magnitude, and subtracting it '
                 'from the apparent magnitude gives the distance through the distance modulus, with '
                 'no geometric parallax needed.',
                 ['spectroscopic parallax', 'absolute magnitude', 'distance']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 9
    {
        'unit': 'Stellar Atmospheres & Interiors',
        'about': 'Solves the interior of a star with four structure equations, then tests the '
                 'solution on the Sun.',
        'sections': [
            ('astronomy', '15-1-the-structure-and-composition-of-the-sun'),
            ('astronomy', '16-1-sources-of-sunshine-thermal-and-gravitational-energy'),
            ('astronomy', '16-3-the-solar-interior-theory'),
            ('astronomy', '16-4-the-solar-interior-observations'),
        ],
        'topics': [
            ('The Radiation Field: Intensity, Flux & Radiation Pressure', [
                ('Specific Intensity, Flux and Radiation Pressure',
                 'Specific intensity, the energy per area, time, solid angle and frequency, is '
                 'conserved along a ray in vacuum, flux follows F = integral of I cos(theta) dOmega '
                 'and falls as 1/d^2, and radiation pressure 4 sigma T^4/(3c) balances gravity at '
                 'the Eddington luminosity.',
                 ['specific intensity', 'flux', 'radiation pressure']),
            ]),
            ('Opacity, Mean Free Path & Optical Depth', [
                ('Opacity, Optical Depth and Mean Free Path',
                 'Optical depth, the integral of kappa rho ds, counts the mean free paths a photon '
                 'crosses, so the photosphere is by definition where that depth reaches 1 and the '
                 'mean free path is 1/(kappa rho).',
                 ['opacity', 'optical depth', 'mean free path']),
            ]),
            ('Radiative Transfer, the Gray Atmosphere & Line Formation', [
                ('The Radiative Transfer Equation',
                 'Along a ray dI/ds = -kappa rho I + j, and in local thermodynamic equilibrium the '
                 'source function equals the Planck function, so emergent intensity is B_nu '
                 'averaged over the last unit of optical depth.',
                 ['radiative transfer', 'source function', 'local equilibrium']),
                ('Limb Darkening in a Gray Atmosphere',
                 'A grazing ray reaches optical depth 1 in a cooler, higher layer, so the solar '
                 'disc darkens towards the limb, and the Eddington grey atmosphere predicts '
                 'I(mu)/I(1) = (2 + 3 mu)/5 for mu = cos(theta).',
                 ['limb darkening', 'gray atmosphere', 'photosphere']),
            ]),
            ('Hydrostatic Equilibrium & the Equation of State', [
                ('Hydrostatic Equilibrium and Central Conditions',
                 'Each layer balances pressure against weight, dP/dr = -G M_r rho/r^2, which for '
                 'the Sun implies a central pressure near 10^16 Pa and a central temperature near '
                 '1.5x10^7 K.',
                 ['hydrostatic equilibrium', 'pressure gradient', 'central temperature']),
            ]),
            ('Nuclear Energy Generation', [
                ('The Proton-Proton Chain and the CNO Cycle',
                 'Hydrogen fusion yields 26.7 MeV per helium nucleus, and the proton-proton chain '
                 'dominates below about 1.3 solar masses while the far steeper CNO cycle takes over '
                 'in more massive stars.',
                 ['pp chain', 'cno cycle', 'hydrogen fusion']),
            ]),
            ('Energy Transport: Radiative Diffusion & Convection', [
                ('Radiative Diffusion and Convection',
                 'Radiative transport is a random walk that takes about 10^5 years to cross the '
                 'solar interior, while convection takes over where the gradient exceeds the '
                 'adiabatic one and carries the outer envelope in weeks to months.',
                 ['radiative diffusion', 'convection', 'random walk']),
            ]),
            ('Stellar Structure Equations, the Virial Theorem & Timescales', [
                ('The Virial Theorem',
                 'For a bound, non-relativistic system 2K + Omega = 0, so half the energy released '
                 'by contraction is radiated and half raises the internal temperature, which is why '
                 'a collapsing cloud heats up.',
                 ['virial theorem', 'contraction', 'binding energy']),
                ('The Three Stellar Timescales',
                 'The dynamical time sqrt(R^3/GM) is about 30 minutes for the Sun, the '
                 'Kelvin-Helmholtz time about 3x10^7 years and the nuclear time about 10^10 years, '
                 'which is why the Sun sits stably on the main sequence.',
                 ['dynamical timescale', 'kelvin-helmholtz', 'nuclear timescale']),
            ]),
            ('The Sun as the Calibrating Standard Model', [
                ('The Standard Solar Model',
                 'A model with 1.989x10^30 kg, 6.96x10^8 m, 3.83x10^26 W and 5 772 K reproduces '
                 'the observed p-mode frequencies and the 8.8 MeV boron-8 neutrino flux, which is '
                 'how the interior solution is tested.',
                 ['standard solar model', 'helioseismology', 'solar neutrinos']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 10
    {
        'unit': 'Star Formation, Evolution & the ISM',
        'about': 'Follows gas from a cold molecular cloud to a main-sequence star and on to the '
                 'red-giant and supergiant stages.',
        'sections': [
            ('astronomy', '20-1-the-interstellar-medium'),
            ('astronomy', '21-1-star-formation'),
            ('astronomy', '22-1-evolution-from-the-main-sequence-to-red-giants'),
            ('astronomy', '22-2-star-clusters'),
        ],
        'topics': [
            ('The Interstellar Medium', [
                ('Phases of the Interstellar Medium',
                 'The interstellar medium ranges from molecular clouds at 10 to 20 K and 10^2 to '
                 '10^6 particles per cm^3, through warm neutral gas near 8 000 K, to hot ionised '
                 'gas above 10^6 K, the phases held in rough pressure balance.',
                 ['interstellar medium', 'molecular cloud', 'phases']),
            ]),
            ('Star Formation & Collapse', [
                ('The Jeans Mass and Gravitational Collapse',
                 'A cloud collapses only when its mass exceeds the Jeans mass, which scales as '
                 'T^(3/2) rho^(-1/2), so cold dense cores collapse while warm diffuse gas does '
                 'not.',
                 ['jeans mass', 'gravitational collapse', 'molecular cloud']),
                ('Protostars, Accretion Discs and Outflows',
                 'A collapsing core conserves angular momentum, so it flattens into a disc, drives '
                 'bipolar outflows along the rotation axis, and reaches the main sequence only '
                 'after a Kelvin-Helmholtz time of some 3x10^7 years at one solar mass.',
                 ['protostar', 'accretion disc', 'bipolar outflow']),
            ]),
            ('Main-Sequence Evolution', [
                ('Main-Sequence Lifetimes',
                 'A star burns core hydrogen for about 10^10 (M/M_sun)^(-2.5) years, so a ten '
                 'solar mass star lasts 3x10^7 years and a half-solar-mass star about 6x10^10 '
                 'years.',
                 ['main sequence', 'stellar lifetime', 'hydrogen burning']),
            ]),
            ('Post-Main-Sequence Evolution', [
                ('Red Giants and the Helium Flash',
                 'Once core hydrogen is spent the core contracts and the envelope swells to 10 to '
                 '100 solar radii, and a one-solar-mass star ignites helium in a degenerate-core '
                 'flash before settling onto the horizontal branch.',
                 ['red giant', 'helium flash', 'horizontal branch']),
            ]),
            ('Star Clusters as Evolutionary Clocks', [
                ('The Main-Sequence Turnoff Age',
                 "Because lifetime scales as M^(-2.5), a cluster's turnoff mass dates it, so the "
                 "turnoff luminosity read from the colour-magnitude diagram is the cluster's clock.",
                 ['turnoff', 'cluster age', 'isochrone']),
                ('Open versus Globular Clusters',
                 'Open clusters are young, metal-rich disc systems of 10^2 to 10^3 stars, whereas '
                 'globular clusters are ancient metal-poor haloes of 10^5 to 10^6 stars whose '
                 'turnoffs sit below the solar mass.',
                 ['open cluster', 'globular cluster', 'stellar population']),
            ]),
            ('Nucleosynthesis & Chemical Enrichment', [
                ('Stellar Nucleosynthesis and Metallicity',
                 'Fusion builds elements up to iron, elements beyond iron need neutron capture in '
                 "AGB stars and supernovae, and each generation's ejecta raise the metallicity of "
                 'the gas the next stars form from.',
                 ['nucleosynthesis', 'metallicity', 'chemical enrichment']),
            ]),
            ('Stellar Pulsation & Variable Stars', [
                ('The Period-Density Relation for Pulsators',
                 'A pulsating star obeys a constant product of period and the square root of mean '
                 'density, so the period fixes that density and a Cepheid with a ten-day period has '
                 'a radius of order 10^2 solar radii.',
                 ['pulsation', 'cepheid', 'period-density']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 11
    {
        'unit': 'Stellar Death & Compact Objects',
        'about': 'Carries the evolution past the endpoint, where degeneracy, relativity and '
                 'accretion set the physics.',
        'sections': [
            ('astronomy', '23-1-the-death-of-low-mass-stars'),
            ('astronomy', '23-2-evolution-of-massive-stars-an-explosive-finish'),
            ('astronomy', '23-4-pulsars-and-the-discovery-of-neutron-stars'),
            ('astronomy', '24-5-black-holes'),
        ],
        'topics': [
            ('Supernovae & Their Aftermath', [
                ('Core-Collapse and Thermonuclear Supernovae',
                 'A star above about eight solar masses ends in a core-collapse supernova that '
                 'releases near 10^46 J and leaves a neutron star or black hole, while a Type Ia '
                 'comes from a white dwarf reaching 1.4 solar masses and is standardisable for '
                 'cosmology.',
                 ['supernova', 'core collapse', 'type ia']),
            ]),
            ('White Dwarfs & Electron Degeneracy', [
                ('White Dwarf Degeneracy and Cooling',
                 'Electron degeneracy pressure holds a white dwarf near 0.01 solar radii only '
                 'below the Chandrasekhar mass of 1.4 solar masses, and with no fusion source the '
                 'star then cools along a sequence whose faint end dates its cluster.',
                 ['white dwarf', 'degeneracy pressure', 'chandrasekhar limit']),
            ]),
            ('Neutron Stars & Pulsars', [
                ('Neutron Star Structure and the Pulsar Beam',
                 'A neutron star puts 1.4 solar masses inside a 10 km radius at nuclear density '
                 'near 10^17 kg/m^3, and a misaligned magnetic dipole beams radiation that sweeps '
                 'past Earth once per rotation.',
                 ['neutron star', 'pulsar', 'magnetic dipole']),
            ]),
            ('Relativity, Schwarzschild Geometry & Black Holes', [
                ('The Schwarzschild Radius and Event Horizon',
                 'The Schwarzschild radius 2GM/c^2 is 3 km per solar mass, so a ten-solar-mass '
                 'black hole has a 30 km horizon and a clock hovering at twice that radius ticks at '
                 '1/sqrt(2) of the rate at infinity.',
                 ['schwarzschild radius', 'event horizon', 'black hole']),
            ]),
            ('Accretion & Interacting Binaries', [
                ('Accretion Discs and the Eddington Limit',
                 'Accretion liberates GM(dM/dt)/R, so a neutron star accreting 10^-8 solar masses '
                 'per year radiates about 10^31 W, and the Eddington limit caps how fast a compact '
                 'object can be fed.',
                 ['accretion disc', 'x-ray binary', 'eddington limit']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 12
    {
        'unit': 'The Milky Way & Galaxies',
        'about': 'Moves from our own galaxy outward to morphology, distances, clusters and the '
                 'active nuclei at galactic centres.',
        'sections': [
            ('astronomy', '25-1-the-architecture-of-the-galaxy'),
            ('astronomy', '26-2-types-of-galaxies'),
            ('astronomy', '26-4-the-extragalactic-distance-scale'),
            ('astronomy', '27-1-quasars'),
        ],
        'topics': [
            ('The Milky Way Galaxy', [
                ('Structure and Rotation of the Milky Way',
                 'The Galaxy is a barred spiral about 30 kpc across with the Sun 8 kpc from the '
                 'centre, and its rotation curve stays near 220 km/s far beyond the visible disc, '
                 'which implies a dark halo of several times the visible mass.',
                 ['milky way', 'rotation curve', 'dark matter']),
            ]),
            ('Galaxy Morphology & Structure', [
                ('The Hubble Sequence',
                 'Galaxies divide into ellipticals, lenticulars, spirals and irregulars along the '
                 'Hubble sequence, which orders them by the balance of bulge and disc rather than '
                 'by a single evolutionary path.',
                 ['hubble sequence', 'morphology', 'elliptical galaxy']),
            ]),
            ('The Extragalactic Distance Ladder', [
                ('Cepheids as Standard Candles',
                 'The period-luminosity law makes a Cepheid a standard candle, so a ten-day '
                 'Cepheid near 3x10^3 solar luminosities has its distance fixed by its period and '
                 'apparent brightness to a few per cent.',
                 ['cepheid', 'period-luminosity', 'standard candle']),
                ('The Distance Ladder and Its Systematics',
                 'Parallax, Cepheids, the red-giant tip, the Tully-Fisher relation and Type Ia '
                 'supernovae calibrate one another in sequence, so an error at one rung propagates '
                 'into every distance above it.',
                 ['distance ladder', 'tully-fisher', 'calibration']),
            ]),
            ('Galaxy Formation & Evolution', [
                ('Hierarchical Assembly in a Dark Matter Universe',
                 'Structure grows bottom-up through mergers in a cold dark matter universe, so '
                 'large galaxies are assembled from smaller pieces and their star formation peaks '
                 'near redshift 2.',
                 ['hierarchical formation', 'mergers', 'star formation history']),
            ]),
            ('Galaxy Clusters & Large-Scale Structure', [
                ('Clusters, Groups and the Cosmic Web',
                 'A galaxy cluster holds 10^2 to 10^3 galaxies within a few Mpc and is dominated by '
                 '10^7 to 10^8 K intracluster gas and dark matter, and clusters trace the filaments '
                 'and voids of the cosmic web.',
                 ['galaxy cluster', 'cosmic web', 'intracluster gas']),
            ]),
            ('Active Galaxies & AGN', [
                ('The Unified Model of Active Galactic Nuclei',
                 'An active nucleus is powered by accretion onto a supermassive black hole, and '
                 'the viewing angle through the dusty torus explains why one engine appears as a '
                 'Seyfert galaxy, a quasar or a blazar.',
                 ['active galactic nuclei', 'quasar', 'unified model']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 13
    {
        'unit': 'Cosmology & the Early Universe',
        'about': 'Applies gravity and thermodynamics to the whole universe, from the expansion law '
                 'to the first three minutes.',
        'sections': [
            ('astronomy', '29-1-the-age-of-the-universe'),
            ('astronomy', '29-2-a-model-of-the-universe'),
            ('astronomy', '29-4-the-cosmic-microwave-background'),
            ('astronomy', '29-6-the-inflationary-universe'),
        ],
        'topics': [
            ("Cosmic Expansion & Hubble's Law", [
                ("Hubble's Law and the Hubble Constant",
                 'Recession grows with distance as v = H0 d, so H0 near 70 km/s/Mpc puts a galaxy '
                 'at 100 Mpc at 7 000 km/s and gives a Hubble time of about 14 Gyr.',
                 ['hubble law', 'hubble constant', 'recession']),
                ('Cosmological Redshift and the Scale Factor',
                 'Cosmological redshift obeys 1 + z = a_observed/a_emitted, so z = 1 means the '
                 'light left when the universe was half its present size.',
                 ['redshift', 'scale factor', 'lookback time']),
            ]),
            ('Scale Factor, Critical Density & the Fate of the Universe', [
                ('The Critical Density and Omega',
                 'The critical density 3H0^2/(8 pi G) is about 9x10^-27 kg/m^3 for H0 = 70 '
                 'km/s/Mpc, and the ratio Omega = rho/rho_c decides whether the spatial geometry '
                 'is closed, flat or open.',
                 ['critical density', 'omega', 'geometry']),
                ('The Friedmann Equation and Accelerating Expansion',
                 'The Friedmann equation ties the expansion rate to density and curvature, and the '
                 'data since 1998 require a dark-energy density near 0.7, so the expansion '
                 'accelerates instead of slowing.',
                 ['friedmann equation', 'dark energy', 'acceleration']),
            ]),
            ('The Cosmic Microwave Background', [
                ('The CMB and Its Acoustic Peaks',
                 'The cosmic microwave background is a 2.725 K blackbody released at recombination '
                 'near redshift 1 100, and its acoustic peaks fix a flat geometry and the baryon '
                 'fraction.',
                 ['cmb', 'recombination', 'acoustic peaks']),
            ]),
            ('Big Bang Nucleosynthesis', [
                ('Big Bang Nucleosynthesis and the Light Elements',
                 'Within the first few minutes, as kT fell below about 1 MeV, nucleosynthesis left '
                 'roughly 75 per cent hydrogen, 25 per cent helium-4 and traces of deuterium and '
                 'lithium-7, which fixes the baryon-to-photon ratio.',
                 ['big bang nucleosynthesis', 'helium abundance', 'baryon density']),
            ]),
            ('Dark Energy & Accelerating Expansion', [
                ('Dark Energy and the Equation of State',
                 'Dark energy supplies about 68 per cent of the energy budget with an equation of '
                 'state w = p/(rho c^2) consistent with -1, which is why the expansion accelerates '
                 'although gravity pulls inward.',
                 ['dark energy', 'cosmological constant', 'equation of state']),
            ]),
            ('Inflation & the Horizon and Flatness Problems', [
                ('Inflation and the Horizon and Flatness Problems',
                 'An epoch of exponential expansion by at least e^60 explains how causally '
                 'disconnected patches share one background temperature and why Omega is driven so '
                 'close to 1.',
                 ['inflation', 'horizon problem', 'flatness problem']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 14
    {
        'unit': 'The Solar System & Exoplanets',
        'about': 'Closes the course by applying stellar and orbital physics to planetary systems, '
                 'including the thousands now known around other stars.',
        'sections': [
            ('astronomy', '7-1-overview-of-our-planetary-system'),
            ('astronomy', '10-1-the-nearest-planets-an-overview'),
            ('astronomy', '11-2-the-giant-planets'),
            ('astronomy', '21-4-planets-beyond-the-solar-system-search-and-discovery'),
        ],
        'topics': [
            ('Solar System Orbital Phenomena', [
                ('Oppositions, Synodic Periods and Retrograde Loops',
                 "A planet's synodic period with Earth follows 1/S = 1/P_planet - 1/P_Earth, "
                 'giving 780 days for Mars, and the geometry of Earth catching up produces the '
                 'opposition and its retrograde loop.',
                 ['opposition', 'synodic period', 'retrograde']),
            ]),
            ('The Terrestrial Planets', [
                ('Comparative Geology of the Terrestrial Planets',
                 'Mercury, Venus, Earth and Mars share a rocky differentiated composition but '
                 'differ in atmosphere and surface because planet size sets whether gas is '
                 'retained and whether plate tectonics or volcanism dominates.',
                 ['terrestrial planets', 'differentiation', 'atmosphere']),
            ]),
            ('The Giant Planets', [
                ('The Giant Planets and Their Interiors',
                 'Jupiter and Saturn are 318 and 95 Earth masses of hydrogen and helium with '
                 'metallic-hydrogen interiors, Uranus and Neptune are 14 to 17 Earth-mass ice '
                 'giants, and all four lack a solid surface and carry strong magnetic fields.',
                 ['giant planets', 'metallic hydrogen', 'ice giants']),
            ]),
            ('Minor Bodies of the Solar System', [
                ('Asteroids, Comets and the Kuiper Belt',
                 'Main-belt asteroids orbit between 2.2 and 3.3 au, comets arrive from the Kuiper '
                 "belt and Oort cloud and grow tails only inside about 5 au, and the belt's total "
                 "mass is under a thousandth of Earth's.",
                 ['asteroids', 'comets', 'kuiper belt']),
            ]),
            ('Formation of Planetary Systems', [
                ('The Protoplanetary Disc and Planetesimal Accretion',
                 'A protoplanetary disc builds planetesimals from sticky grains and then cores by '
                 'runaway accretion, and beyond the snow line near 3 au cores grow fast enough to '
                 'capture hydrogen before the gas disperses in a few million years.',
                 ['protoplanetary disc', 'planetesimal', 'snow line']),
            ]),
            ('Exoplanet Detection', [
                ('The Transit Method',
                 'A transiting planet dims its star by (R_p/R_star)^2, so a Jupiter across a '
                 'Sun-like star gives a one per cent dip, and a hot Jupiter at 0.05 au repeats '
                 'every four days.',
                 ['transit', 'photometry', 'hot jupiter']),
                ('The Radial-Velocity Method',
                 'The stellar reflex motion has semi-amplitude proportional to m_p sin(i)/M_star '
                 'times (2 pi G/P)^(1/3), so Jupiter moves the Sun by 12.5 m/s while Earth moves '
                 'it by 9 cm/s.',
                 ['radial velocity', 'reflex motion', 'minimum mass']),
            ]),
        ],
    },
]
