"""Earth and Space Science outline, in the shape ``scripts/course_pipeline.py`` expects.

A ten-unit, full-year Earth Science course written for this project: the practices and
reference tools of the discipline, plate tectonics and the interior, minerals and rocks,
volcanoes and earthquakes, geologic time and Earth history, weathering and water, oceans
and ice, atmosphere and climate, resources and hazards, and Earth's place in the solar
system. Unit and topic names follow the course plan; every summary below is an original
statement written here, not textbook text.

Textbook position. OpenStax publishes no Earth Science textbook, and this module does not
borrow Astronomy, Biology or Chemistry as a stand-in anchor: a link that does not teach the
unit would be a fabricated citation. ``TEXTBOOK`` therefore declares
``no_cc_by_anchor = True`` with the reason, every unit carries an empty ``sections`` list,
and ``course_pipeline.py verify`` reports the anchoring check as SKIP with that reason
instead of a green tick it has not earned. The external study links the course carries
(OpenStax Astronomy, Khan Academy, and NASA, NOAA and USGS material) stay link-only: none
is fetched, stored or quoted, and none appears as a section.

Unit 10 legitimately overlaps astronomy. It is kept on Earth's place in the universe and on
the Earth-Sun-Moon geometry that drives seasons, eclipses and tides, so it is not a second
astronomy course: stellar and galactic content appears only to the depth needed to explain
where Earth's matter and its energy budget come from.
"""

from __future__ import annotations

ID = 'earth_space_science'
TITLE = 'Earth and Space Science'
SUBJECT = 'Earth Science'
SUBJECT_KIND = 'science'
EXPECTED_WEEKS = 36
COURSE_LINE = 'Earth and Space Science - Systems, Cycles and Evidence'
DESCRIPTION = (
    'A full-year Earth Science course: the practices and reference tools of the discipline, '
    "Earth's interior and plate tectonics, minerals, rocks and the rock cycle, volcanoes, "
    'earthquakes and crustal deformation, geologic time and Earth history, weathering, '
    'streams and groundwater, oceans, coasts and glaciers, the atmosphere, weather and '
    'climate, resources, hazards and sustainability, and Earth\'s place in the solar system.')

TEXTBOOK = {
    'spine': '',
    'supplements': [],
    'link_only_note': '',
    'no_cc_by_anchor': True,
    'reason': ('OpenStax publishes no Earth Science textbook; the catalogue was checked '
               'on 2026-11-10. The outline is an original CC0 scope and sequence and is '
               'not anchored to a textbook, so no section is quoted for this course.'),
}

UNITS = [
    # ------------------------------------------------------------------ 1
    {
        'unit': 'Earth Science Practices and Reference Tools',
        'about': ('The entry unit: how an Earth science claim is made and checked, the '
                  'four spheres and the two energy engines behind them, and the '
                  'reference tables, formulas and maps every later unit reads from.'),
        'sections': [],
        'topics': [
            ('Science Practices and Evidence', [
                ('Observation, Inference, and Explanation',
                 'An observation is what an instrument or a sense directly detects while an '
                 'inference is an explanation built from it, so a statement about why a layer '
                 'formed is an inference and must be checked against evidence other than the '
                 'layer itself.',
                 ['observation', 'inference', 'evidence']),
                ('Hypotheses, Models, and Testable Predictions',
                 'A hypothesis is an explanation phrased so that a prediction follows from it, '
                 'and because most Earth processes cannot be run as a laboratory experiment the '
                 'hypothesis is tested by comparing a model\'s prediction with field data such '
                 'as measured plate motion.',
                 ['hypothesis', 'model', 'prediction']),
                ('Uncertainty, Replication, and Peer Review',
                 'Every measurement carries a stated uncertainty range, so a conclusion is '
                 'accepted only when independent measurements agree within those ranges and '
                 'another worker can reproduce the result.',
                 ['uncertainty', 'replication', 'peer review']),
            ]),
            ('Earth Systems, Scale, and Interaction', [
                ('The Four Spheres and Their Exchange at Boundaries',
                 'The geosphere, hydrosphere, atmosphere and biosphere exchange matter and '
                 'energy across their boundaries, so a volcanic eruption moves gases and ash '
                 'from the geosphere into the atmosphere and can cool climate for a year or '
                 'more.',
                 ['earth systems', 'sphere', 'exchange']),
                ('Two Energy Engines: Sun and Interior',
                 'Solar radiation drives the atmosphere, ocean and water cycle from outside '
                 'while radioactive decay and residual heat of accretion drive tectonics from '
                 'inside, so a landscape records both surface and interior processes at once.',
                 ['energy budget', 'solar radiation', 'internal heat']),
                ('Scale, Rate, and the Geologic Record',
                 'Earth processes run at rates from millimetres per year to minutes, so a '
                 'canyon cut over millions of years and a flood that moves its sediment in a '
                 'day are successive chapters of one landscape history rather than opposites.',
                 ['scale', 'rate', 'geologic time']),
            ]),
            ('Reference Tables, Units, and Formula Tools', [
                ('Reading the Earth Science Reference Tables',
                 'The reference tables collect the constants, mineral and rock properties and '
                 'chart scales used throughout the course, so a value must be taken from the '
                 'correct row and kept with its stated unit, because density for example is '
                 'listed in grams per cubic centimetre.',
                 ['reference tables', 'data table', 'chart']),
                ('Unit Conversion and Scientific Notation',
                 'A unit is converted by multiplying by a ratio equal to one, as one kilometre '
                 'over one thousand metres does, so 3,500 metres becomes 3.5 kilometres, and '
                 'very large or small quantities are written as powers of ten.',
                 ['unit conversion', 'scientific notation', 'si units']),
                ('Gradient, Rate of Change, and Density',
                 'Gradient is the change in a field value divided by distance, rate of change is '
                 'change divided by time and density is mass divided by volume, so each result '
                 'carries combined units such as metres per kilometre or grams per cubic '
                 'centimetre rather than a bare number.',
                 ['gradient', 'rate of change', 'density']),
            ]),
            ('Maps, Coordinates, and Profiles', [
                ('Latitude, Longitude, and Map Position',
                 'Latitude is measured north or south of the equator from 0 to 90 degrees and '
                 'longitude east or west of the prime meridian from 0 to 180, and because '
                 'meridians converge at the poles a degree of longitude narrows from about 111 '
                 'kilometres at the equator to zero at the poles.',
                 ['latitude', 'longitude', 'coordinates']),
                ('Contour Lines, Relief, and Profiles',
                 'Contour lines join points of equal elevation, so closely spaced lines mark a '
                 'steep slope, hachured contours mark a depression, and a contour bending '
                 'upstream marks a valley floor.',
                 ['contour line', 'topographic map', 'elevation']),
            ]),
            ('Data Displays, Trends, and Reliability', [
                ('Choosing a Display for Earth Data',
                 'Categories are compared with a bar chart, a quantity tracked through time is '
                 'plotted as a line, and two measured variables are plotted against each other '
                 'as a scatter, so a mismatched display hides the pattern the data actually '
                 'contain.',
                 ['data display', 'graph', 'scatter plot']),
                ('Cycles, Trends, and Data Reliability',
                 'Many Earth records cycle on daily, seasonal or tidal periods, so a trend can '
                 'be read only after averaging across at least one full cycle, and a conclusion '
                 'drawn from a few scattered measurements stays provisional until more samples '
                 'agree.',
                 ['cycle', 'trend', 'sample size']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 2
    {
        'unit': "Plate Tectonics and Earth's Interior",
        'about': ('The organising theory of the course: the seismic and thermal evidence for '
                  "Earth's layered interior, the evidence that plates move, the boundary "
                  'types those motions produce, and the forces and long-term consequences.'),
        'sections': [],
        'topics': [
            ('Interior Evidence and Layers', [
                ('Seismic Waves as Probes of the Interior',
                 'P waves travel through solids, liquids and gases while S waves travel only '
                 'through solids, so the S-wave shadow zone beyond about 103 degrees from an '
                 'epicenter shows that the outer core is liquid.',
                 ['seismic wave', 'shadow zone', 'outer core']),
                ('Compositional Layers and the Lithosphere',
                 'Earth is divided by composition into crust, mantle and core and by strength '
                 'into a rigid lithosphere over a weak asthenosphere, so the lithosphere is '
                 'crust plus uppermost mantle rather than crust alone, and it is the layer that '
                 'moves as a plate.',
                 ['crust', 'mantle', 'lithosphere']),
                ('Heat Flow, Gravity, and the Geodynamo',
                 'Heat flow is highest at mid-ocean ridges and lowest over old continental '
                 'interiors, and the magnetic field is generated by convection in the liquid '
                 'outer core, so heat flow, gravity and magnetism together constrain any model '
                 'of the interior.',
                 ['heat flow', 'geomagnetic field', 'convection']),
            ]),
            ('Evidence for Plate Tectonics', [
                ('Continental Drift and the Missing Mechanism',
                 'Wegener matched coastlines, fossils and rock sequences across the Atlantic '
                 'but could name no force able to move a continent, so the idea waited until '
                 'seafloor spreading supplied a mechanism, which shows that a correct pattern '
                 'still needs a physical process before it is accepted.',
                 ['continental drift', 'wegener', 'pangaea']),
                ('Seafloor Spreading and Magnetic Stripes',
                 'New oceanic crust forms at a ridge and records the field polarity as it cools, '
                 'so the symmetrical stripes of alternating polarity on either side of the ridge '
                 'record reversals and show that the ocean floor grows outward from the axis.',
                 ['seafloor spreading', 'magnetic reversal', 'mid-ocean ridge']),
                ('GPS, Earthquake Belts, and Paleoclimate Clues',
                 'Satellite geodesy measures plate motion directly at a few centimetres per '
                 'year, earthquakes concentrate in narrow belts rather than at random, and '
                 'glacial deposits now in tropical latitudes mark continents that have drifted.',
                 ['gps', 'earthquake belt', 'paleoclimate']),
            ]),
            ('Plate Boundaries and Map Patterns', [
                ('Divergent Boundaries and Rift Valleys',
                 'Where plates move apart, magma rises to build a mid-ocean ridge with shallow '
                 'earthquakes and basaltic lava, and the same process inside a continent splits '
                 'it into a rift valley such as the East African Rift.',
                 ['divergent boundary', 'rift valley', 'mid-ocean ridge']),
                ('Convergent Boundaries: Subduction and Collision',
                 'Where an oceanic plate meets another plate it subducts and produces a trench '
                 'with a volcanic arc behind it, while where two continents collide neither '
                 'subducts and the crust thickens into fold mountains such as the Himalaya.',
                 ['convergent boundary', 'subduction', 'continental collision']),
                ('Transform Boundaries and Lateral Faulting',
                 'Plates sliding past each other produce shallow earthquakes along a transform '
                 'fault and no volcanism, because no lithosphere is created or destroyed at '
                 'that boundary.',
                 ['transform boundary', 'strike-slip fault', 'san andreas']),
            ]),
            ('Plate Motion Mechanisms', [
                ('Mantle Convection and Slab Pull',
                 'Convection in the mantle supplies the motion, but the dominant force is slab '
                 'pull, in which cold dense subducting lithosphere sinks and drags the rest of '
                 'the plate with it, with ridge push a smaller contribution.',
                 ['mantle convection', 'slab pull', 'ridge push']),
                ('Why Plates Move at Different Speeds',
                 'A plate\'s speed reflects the balance between its driving forces and the '
                 'resistance it meets, so a plate with long subducting margins such as the '
                 'Pacific moves several times faster than one bordered largely by continental '
                 'collision.',
                 ['plate velocity', 'driving force', 'resistance']),
            ]),
            ('Tectonic Features and Long-Term Change', [
                ('Hot Spots and Plate Motion Records',
                 'A mantle plume stays roughly fixed while the plate rides over it, so the plume '
                 'builds a chain of progressively older volcanoes, and the bend in the '
                 'Hawaiian-Emperor chain records a change in the direction of Pacific motion.',
                 ['hot spot', 'mantle plume', 'hawaii']),
                ('Tectonics Controls Topography and Climate',
                 'Uplift builds mountains that cast a rain shadow and expose fresh silicate rock '
                 'to weathering, and silicate weathering consumes carbon dioxide, so tectonic '
                 'uplift can cool global climate over millions of years.',
                 ['orogeny', 'rain shadow', 'silicate weathering']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 3
    {
        'unit': 'Minerals, Rocks, and the Rock Cycle',
        'about': ('The materials layer: how a mineral is defined and identified, how igneous, '
                  'sedimentary and metamorphic rocks form and what each records, and how the '
                  'rock cycle moves material between them.'),
        'sections': [],
        'topics': [
            ('Minerals', [
                ('What Makes a Mineral',
                 'A mineral is naturally occurring, inorganic, solid, has a definite chemical '
                 'composition and an ordered crystal structure, which is why glass lacks the '
                 'structure and coal lacks both the composition and the inorganic origin.',
                 ['mineral', 'crystal structure', 'inorganic']),
                ('Silicate Structure Sets Hardness and Cleavage',
                 'Every silicate is built from SiO4 tetrahedra, and the way those tetrahedra '
                 'link decides cleavage, so isolated tetrahedra in olivine give no cleavage '
                 'while sheets in mica split into thin flat flakes.',
                 ['silicate', 'tetrahedron', 'cleavage']),
                ('Diagnostic Properties and Mineral Formation',
                 'Hardness, cleavage, streak and luster identify a mineral because each reflects '
                 'its composition and structure, and a mineral forms by crystallising from melt, '
                 'precipitating from solution or recrystallising under heat and pressure.',
                 ['hardness', 'streak', 'crystallization']),
            ]),
            ('Igneous Processes and Rocks', [
                ('Magma Composition Sets Eruption Style',
                 'High-silica magma is viscous and traps gas so it erupts explosively, while '
                 'low-silica basaltic magma flows easily and erupts quietly, so silica content '
                 'rather than temperature decides the style of an eruption.',
                 ['silica', 'viscosity', 'magma']),
                ('Cooling Rate Sets Texture',
                 'Slow cooling at depth grows large interlocking crystals in an intrusive rock '
                 'while rapid cooling at the surface gives fine grains or glass, so texture '
                 'records the cooling history of a rock rather than its composition.',
                 ['intrusive', 'extrusive', 'texture']),
            ]),
            ('Sediments and Sedimentary Rocks', [
                ('From Weathering to Lithification',
                 'A clastic rock forms by weathering, transport, deposition and then compaction '
                 'and cementation, so grain rounding and sorting record how far the sediment '
                 'travelled and by which agent rather than how old it is.',
                 ['clastic', 'lithification', 'sorting']),
                ('Chemical and Biochemical Sedimentary Rocks',
                 'Evaporites such as halite and gypsum form where dissolved ions concentrate as '
                 'water evaporates, while limestone forms from calcium carbonate shells or by '
                 'direct precipitation, so each records a water chemistry rather than a current.',
                 ['evaporite', 'limestone', 'precipitation']),
                ('Sedimentary Structures Record Environments',
                 'Cross-beds record migrating ripples, mudcracks record wetting and drying of '
                 'exposed mud and a graded bed records a waning current, so structures identify '
                 'the setting where grain size alone cannot.',
                 ['cross-bedding', 'mudcrack', 'graded bed']),
            ]),
            ('Metamorphic Processes and Rocks', [
                ('Heat, Pressure, and Foliation',
                 'Directed pressure at depth aligns platy minerals perpendicular to the stress, '
                 'so increasing metamorphic grade turns shale into slate, phyllite, schist and '
                 'gneiss, and the foliation records the direction of that pressure.',
                 ['foliation', 'metamorphic grade', 'directed pressure']),
                ('Contact and Regional Metamorphism',
                 'Heat from an intrusion bakes a narrow aureole of non-foliated rock such as '
                 'hornfels, whereas directed pressure across a convergent margin produces '
                 'foliated rock over a belt hundreds of kilometres wide.',
                 ['contact metamorphism', 'regional metamorphism', 'hornfels']),
            ]),
            ('Rock Cycle and Earth Materials Synthesis', [
                ('Tectonics and Water Drive the Rock Cycle',
                 'Melting, metamorphism and uplift are supplied by plate tectonics while '
                 'weathering and erosion are supplied by the water cycle, so a rock converts '
                 'into another type only through one of those processes acting on it.',
                 ['rock cycle', 'plate tectonics', 'weathering']),
                ('The Rock Record Is Incomplete',
                 'Because recycling destroys rock, a missing rock type at an outcrop means only '
                 'that it is absent there, and the oldest surviving rocks are found in stable '
                 'continental interiors where burial and erosion have been least.',
                 ['recycling', 'outcrop', 'unconformity']),
                ('Rock Assemblage Indicates a Past Setting',
                 'A limestone with marine shells records a warm shallow sea, a basalt flow '
                 'records volcanism and a conglomerate of rounded pebbles records a nearby '
                 'highland, so several rock types read together reconstruct a setting.',
                 ['rock assemblage', 'depositional environment', 'indicator']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 4
    {
        'unit': 'Volcanoes, Earthquakes, and Crustal Deformation',
        'about': ('The crust under stress: how magma composition builds different volcanoes, '
                  'how seismic waves locate and size an earthquake, how rock folds and faults, '
                  'and where the resulting hazards concentrate.'),
        'sections': [],
        'topics': [
            ('Volcanoes', [
                ('Shield, Cinder Cone, and Composite Volcanoes',
                 'Low-viscosity basalt builds a broad shield, short gas-rich bursts build a '
                 'steep cinder cone, and alternating ash and viscous lava above a subduction '
                 'zone build a composite cone, so shape records the magma and the setting.',
                 ['shield volcano', 'composite volcano', 'cinder cone']),
                ('Pyroclastic Flows, Ash, and Lahar Hazards',
                 'A pyroclastic flow of hot gas and ash can outrun a car while falling ash '
                 'collapses roofs and shuts airspace, so most volcanic deaths come from flows, '
                 'blasts and lahars rather than from lava.',
                 ['pyroclastic flow', 'ash fall', 'lahar']),
                ('Monitoring Gives Warning, Not Certainty',
                 'Rising seismicity, ground deformation and gas emission precede most eruptions, '
                 'so a monitored volcano can be warned on a scale of days to weeks even though '
                 'the exact onset cannot be predicted.',
                 ['volcano monitoring', 'deformation', 'gas emission']),
            ]),
            ('Earthquakes and Seismic Waves', [
                ('Focus, Epicenter, and Wave Order',
                 'The focus is where rupture begins underground and the epicenter is the point '
                 'on the surface above it, and because P waves are fastest and surface waves '
                 'slowest a station records P before S before the surface waves that do most of '
                 'the damage.',
                 ['focus', 'epicenter', 'p wave']),
                ('Triangulation Locates an Epicenter',
                 'The P-to-S arrival gap grows with distance from the focus, so converting that '
                 'gap to a distance at three stations and drawing three circles fixes the '
                 'epicenter at their single intersection.',
                 ['triangulation', 's-p time', 'seismograph']),
                ('Magnitude, Intensity, and Site Effects',
                 'Magnitude measures energy released on a logarithmic scale where one unit is '
                 'about 32 times more energy while intensity measures shaking and damage at a '
                 'place, and soft saturated sediment amplifies shaking and can liquefy.',
                 ['magnitude', 'intensity', 'liquefaction']),
            ]),
            ('Crustal Deformation and Mountains', [
                ('Stress, Strain, and Brittle or Ductile Response',
                 'Compression shortens rock, tension stretches it and shear twists it, and the '
                 'same rock fractures under shallow cold conditions but folds under deep hot '
                 'ones, so a structure records depth as well as force.',
                 ['stress', 'strain', 'ductile']),
                ('Reading Folds and Faults',
                 'An anticline arches with the oldest beds in its core and a syncline troughs '
                 'with the youngest in its core, while a normal fault drops its hanging wall '
                 'under tension and a reverse fault raises it under compression.',
                 ['anticline', 'normal fault', 'reverse fault']),
                ('Mountain Belts, Isostasy, and Rebound',
                 'Collision thickens the crust so that it floats higher on the mantle, and '
                 'because the crust stays in isostatic balance, removing mass by erosion lets '
                 'the remaining rock rise.',
                 ['isostasy', 'crustal thickening', 'rebound']),
            ]),
            ('Dynamic-Crust Hazard Synthesis', [
                ('Hazard Maps Follow Plate Boundaries',
                 'Subduction zones concentrate the largest earthquakes, tsunamis and explosive '
                 'volcanoes, transform boundaries concentrate shallow earthquakes, and stable '
                 'interiors produce few of either, so a hazard map is drawn along the boundaries.',
                 ['hazard map', 'subduction zone', 'risk']),
                ('Tsunamis and Their Warning',
                 'A megathrust rupture or submarine landslide displaces the water column, and '
                 'the resulting wave is low and fast in open ocean but slows and steepens in '
                 'shallow water, so warning depends on fast seismic detection and deep-ocean '
                 'pressure buoys.',
                 ['tsunami', 'megathrust', 'run-up']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 5
    {
        'unit': 'Geologic Time, Earth History, and Life',
        'about': ('How geologists order and date events: the principles of relative dating, '
                  'correlation by fossils, radiometric ages, the history those methods '
                  'reconstruct, and the regional record of New York.'),
        'sections': [],
        'topics': [
            ('Relative Dating Principles', [
                ('Superposition and Original Horizontality',
                 'In an undisturbed sequence each layer is older than the one above it, and '
                 'because sediment settles horizontally, tilted or folded layers must have been '
                 'disturbed after they were deposited.',
                 ['superposition', 'original horizontality', 'strata']),
                ('Cross-Cutting Relationships and Inclusions',
                 'A fault, intrusion or erosion surface is younger than the rock it cuts, and a '
                 'fragment enclosed in another rock is older than its host, so these relations '
                 'order events without any date at all.',
                 ['cross-cutting', 'inclusion', 'relative age']),
                ('Unconformities Record Missing Time',
                 'An angular unconformity is a tilted eroded sequence buried by flat layers, a '
                 'disconformity is an erosion surface between parallel beds and a nonconformity '
                 'is one cut into igneous or metamorphic rock, so each marks a gap rather than '
                 'continuous deposition.',
                 ['unconformity', 'erosion surface', 'gap']),
            ]),
            ('Correlation and Fossil Evidence', [
                ('Lateral Continuity and Correlation',
                 'A layer extends sideways until its environment ends, so separated outcrops are '
                 'correlated by matching rock type, stacking order and fossil content rather '
                 'than by distance alone.',
                 ['lateral continuity', 'correlation', 'outcrop']),
                ('Index Fossils Date a Bed',
                 'A useful index fossil had a wide geographic range, a short time span and a '
                 'recognisable form, so its presence pins a bed to a narrow interval while a '
                 'long-ranging fossil such as a shark tooth cannot.',
                 ['index fossil', 'fossil range', 'biozone']),
            ]),
            ('Numerical Dating and Time Scale', [
                ('Radioactive Decay and Half-Life',
                 'A radioactive parent decays at a fixed rate, so after one half-life half the '
                 'parent remains and after two a quarter, and the parent-to-daughter ratio dates '
                 'a sample only if the system stayed closed to gain or loss.',
                 ['half-life', 'radioactive decay', 'parent isotope']),
                ('Matching the Isotope to the Material',
                 'Carbon-14 with a 5,730-year half-life dates organic material only to about '
                 '50,000 years while potassium-argon and uranium-lead date volcanic and '
                 'crystalline rock over millions to billions of years, so the wrong isotope gives '
                 'no usable age.',
                 ['carbon-14', 'potassium-argon', 'radiometric dating']),
                ('The Geologic Time Scale',
                 'Eons, eras, periods and epochs are defined by major changes in the fossil '
                 'record, and the Precambrian covers roughly seven-eighths of Earth history, so '
                 'the scale divides time by events rather than into equal parts.',
                 ['geologic time scale', 'period', 'precambrian']),
            ]),
            ('Earth History, Life, and System Change', [
                ('Outgassing, Oceans, and the Rise of Oxygen',
                 'Volcanic outgassing supplied the early atmosphere and condensing water vapour '
                 'formed the oceans, and photosynthesis later raised oxygen enough to oxidise '
                 'iron, which is why banded iron formations lie beneath the red beds.',
                 ['outgassing', 'great oxidation', 'banded iron']),
                ('Mass Extinctions and Their Drivers',
                 'The end-Permian extinction removed about 90 percent of marine species '
                 'alongside the Siberian Traps eruptions and the end-Cretaceous extinction '
                 'coincides with an iridium layer and the Chicxulub impact, so each extinction '
                 'pairs a kill mechanism with a dated cause.',
                 ['mass extinction', 'siberian traps', 'chicxulub']),
                ('Life Alters the Earth System',
                 'Organisms build reefs and shells, bury carbon and release oxygen, so the '
                 'biosphere has changed the atmosphere and the rock record and the two have '
                 'co-evolved rather than life merely adapting to a fixed planet.',
                 ['coevolution', 'biosphere', 'carbon burial']),
            ]),
            ('New York and Regional Geologic History', [
                ("New York's Bedrock Records Three Orogenies",
                 'Grenville metamorphism about 1.1 billion years ago built the Adirondack '
                 'basement, and the Taconic, Acadian and Alleghenian collisions then deformed '
                 'the eastern bedrock of the state in succession.',
                 ['adirondacks', 'taconic orogeny', 'alleghenian']),
                ('Paleozoic Seas and the Catskill Delta',
                 'Shallow Paleozoic seas across New York deposited limestone and shale with '
                 'marine fossils, and erosion of the Acadian mountains built the Catskill delta, '
                 'so the state\'s strata record a shoreline that shifted back and forth.',
                 ['paleozoic', 'devonian', 'catskill delta']),
                ('Pleistocene Ice Shaped the Present Surface',
                 'The Laurentide ice sheet retreated about 20,000 years ago leaving drumlins, '
                 'moraines, erratics and the over-deepened Finger Lakes, so most New York '
                 'landforms are far younger than the bedrock beneath them.',
                 ['laurentide', 'drumlin', 'moraine']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 6
    {
        'unit': 'Weathering, Water, and Landscapes',
        'about': ('The surface system: how rock breaks down, how gravity and water move the '
                  'debris, how streams and groundwater work, and how climate prints itself on '
                  'the shape of the land.'),
        'sections': [],
        'topics': [
            ('Weathering, Erosion, and Soil', [
                ('Mechanical and Chemical Weathering',
                 'Mechanical weathering breaks rock without altering its minerals through frost '
                 'wedging, unloading and abrasion, while chemical weathering alters them by '
                 'hydrolysis, oxidation and carbonation, and each exposes fresh surface that '
                 'speeds the other.',
                 ['mechanical weathering', 'chemical weathering', 'frost wedging']),
                ('Climate Decides Which Weathering Dominates',
                 'Warm wet climates favour chemical weathering and produce clay-rich soil on '
                 'rounded slopes, while cold or dry climates favour mechanical breakdown and '
                 'leave angular debris under thin soil.',
                 ['climate', 'hydrolysis', 'weathering rate']),
                ('Soil Horizons and Formation',
                 'Soil is weathered mineral matter mixed with organic matter, water and air and '
                 'developed into O, A, B and C horizons, and its depth and fertility depend on '
                 'climate, parent material, slope and the time it has had to form.',
                 ['soil', 'horizon', 'parent material']),
            ]),
            ('Mass Wasting', [
                ('When Slopes Fail',
                 'Water adds weight and raises pore pressure while undercutting a slope removes '
                 'its toe support, so a slope fails when the driving stress exceeds the shear '
                 'strength of its material.',
                 ['mass wasting', 'pore pressure', 'slope stability']),
                ('Types and Triggers of Mass Movement',
                 'Creep is slow, a slump rotates, a debris flow is fast and water-rich and a '
                 'rockfall is free fall, and heavy rain, earthquakes and vegetation removal '
                 'trigger them by raising load or lowering strength.',
                 ['creep', 'debris flow', 'trigger']),
            ]),
            ('Streams, Rivers, and Floods', [
                ('Stream Work along a Profile',
                 'A stream erodes where it is steep and fast, carries its load and deposits '
                 'where velocity falls, so a graded stream adjusts its slope until erosion and '
                 'deposition balance toward base level.',
                 ['stream', 'base level', 'sediment load']),
                ('Meanders, Floodplains, and Deltas',
                 'A stream erodes the outer bank of a bend and deposits a point bar on the inner '
                 'bank, so meanders migrate and may be cut off as oxbows, while a delta builds '
                 'where the stream enters standing water and drops its load.',
                 ['meander', 'point bar', 'delta']),
                ('Flood Frequency and Land-Use Effects',
                 'A 100-year flood has a one percent chance in any year rather than arriving once '
                 'a century, and paving a watershed raises peak discharge because rain runs off '
                 'instead of soaking in.',
                 ['flood', 'recurrence interval', 'runoff']),
            ]),
            ('Hydrologic Cycle and Water Budgets', [
                ('The Water Budget Equation',
                 'For a watershed, precipitation equals evapotranspiration plus runoff plus the '
                 'change in storage, so a persistent deficit lowers the water table while a '
                 'surplus raises streamflow and recharge.',
                 ['water budget', 'evapotranspiration', 'storage']),
                ('Runoff, Infiltration, and Watershed Response',
                 'Infiltration depends on soil texture, vegetation, slope and rainfall intensity, '
                 'so a compacted or saturated surface turns rain into flash runoff that a porous '
                 'forest soil would have absorbed.',
                 ['infiltration', 'runoff', 'watershed']),
            ]),
            ('Groundwater and Karst', [
                ('Porosity, Permeability, and the Water Table',
                 'Porosity is the fraction of void space while permeability is how well those '
                 'voids connect, so clay can be porous yet hold water instead of yielding it, '
                 'and the water table is the top of the saturated zone.',
                 ['porosity', 'permeability', 'water table']),
                ('Aquifers, Wells, and Overdraft',
                 'A pumped well draws down a cone of depression whose shape depends on '
                 'permeability, and pumping faster than recharge lowers the regional water table, '
                 'dries shallow wells and can draw salt water inland at a coast.',
                 ['aquifer', 'cone of depression', 'overdraft']),
                ('Karst, Caves, and Sinkholes',
                 'Carbonic acid dissolves limestone along joints into caves, sinkholes and '
                 'streams that vanish underground, so a falling water table can leave a cave roof '
                 'unsupported beneath a road.',
                 ['karst', 'sinkhole', 'limestone dissolution']),
            ]),
            ('Landscapes, Wind, and Deserts', [
                ('Climate Shapes the Landscape',
                 'Humid landscapes are rounded with thick soil and an integrated drainage '
                 'network, while arid landscapes are angular with thin regolith and internal '
                 'drainage, so climate can be read from the shape of the land.',
                 ['landscape', 'humid climate', 'arid climate']),
                ('Wind Erosion and Deposition',
                 'Wind sorts fine material and abrades rock, building dunes whose cross-beds dip '
                 'downwind and blanketing distant ground with loess, so wind deposits are well '
                 'sorted and fine grained.',
                 ['deflation', 'sand dune', 'loess']),
                ('Deserts, Alluvial Fans, and Playas',
                 'An arid basin collects coarse sediment in an alluvial fan at the mountain front '
                 'and dissolved salts in a playa at its centre, so internal drainage concentrates '
                 'minerals instead of carrying them to the sea.',
                 ['alluvial fan', 'playa', 'internal drainage']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 7
    {
        'unit': 'Oceans, Coasts, and Ice',
        'about': ('The water-covered majority of the planet: the shape and chemistry of the '
                  'ocean basins, the circulation that moves heat, the coast where land meets '
                  'water, ice as a landform agent, and the cryosphere feedbacks that matter now.'),
        'sections': [],
        'topics': [
            ('Ocean Basins and Ocean Water', [
                ('Seafloor Provinces',
                 'A continental margin runs from shelf through slope and rise to the abyssal '
                 'plain, and a passive margin carries a wide shelf while an active margin has a '
                 'narrow shelf and a trench, so basin shape records the plate setting.',
                 ['continental shelf', 'abyssal plain', 'continental margin']),
                ('Salinity and Density Structure',
                 'Seawater averages about 35 parts per thousand of dissolved salt and grows '
                 'denser as it becomes colder or saltier, so cold polar water sinks beneath '
                 'warmer water and the ocean stratifies by density.',
                 ['salinity', 'density', 'thermocline']),
                ("The Ocean's Salt Budget",
                 'Rivers deliver dissolved ions from weathering while evaporation removes water '
                 'and hydrothermal circulation and sediment trap ions, so ocean salinity has held '
                 'near its present value over long spans of time.',
                 ['salt budget', 'weathering', 'evaporation']),
            ]),
            ('Ocean Motion and Circulation', [
                ('Surface Currents and Gyres',
                 'Prevailing winds plus the Coriolis effect drive large circular gyres with '
                 'narrow fast western boundary currents such as the Gulf Stream and broad slow '
                 'eastern currents, so surface circulation carries heat poleward.',
                 ['gyre', 'coriolis effect', 'gulf stream']),
                ('Upwelling and Coastal Productivity',
                 'Wind blowing along a coast moves surface water offshore so deeper nutrient-rich '
                 'water rises to replace it, which is why coastal upwelling zones support the '
                 'most productive fisheries.',
                 ['upwelling', 'nutrient', 'productivity']),
                ('Thermohaline Circulation and Climate',
                 'Cold salty water sinking in the North Atlantic drives a slow overturning '
                 'circulation with a timescale near a thousand years, so a large freshwater input '
                 'that freshens the surface can weaken it.',
                 ['thermohaline circulation', 'deep water', 'overturning']),
            ]),
            ('Coasts and Sea-Level Change', [
                ('Wave Refraction and Longshore Drift',
                 'Waves refract until they meet the shore nearly head-on and the resulting '
                 'longshore current carries sand along the beach, so a groin traps sand on its '
                 'updrift side and starves the beach downdrift.',
                 ['wave refraction', 'longshore drift', 'groin']),
                ('Sea Level Change and Coastal Response',
                 'Eustatic sea level rises with melting land ice and warming water while '
                 'isostatic change moves the land itself, so a subsiding coast drowns its river '
                 'valleys while a rebounding coast exposes raised beaches.',
                 ['eustatic', 'isostatic', 'submergent coast']),
            ]),
            ('Glaciers and Glacial Landforms', [
                ('Glacier Mass Balance and Flow',
                 'A glacier advances when accumulation exceeds ablation and retreats when '
                 'ablation exceeds accumulation, and it flows by internal deformation plus basal '
                 'sliding, so terminus position records mass balance rather than temperature '
                 'alone.',
                 ['mass balance', 'ablation', 'glacier flow']),
                ('Erosional Glacial Landforms',
                 'Ice widens a stream-cut V into a U-shaped valley, scoops cirques and horns at '
                 'its head and scratches the bedrock beneath it, so striations and their '
                 'orientation record the path the ice followed.',
                 ['u-shaped valley', 'cirque', 'striation']),
                ('Depositional Glacial Landforms',
                 'Ice drops unsorted till as moraines and drumlins while meltwater carries sorted '
                 'sand and gravel into outwash and eskers, so sorting separates ice-laid from '
                 'water-laid sediment.',
                 ['till', 'moraine', 'outwash']),
            ]),
            ('Ice, Oceans, and Cryosphere Feedbacks', [
                ('Ice-Albedo Feedback',
                 'Snow and ice reflect most incoming sunlight while open ocean absorbs most of '
                 'it, so melting ice exposes a darker surface that absorbs more energy and drives '
                 'further warming.',
                 ['albedo', 'ice-albedo feedback', 'melting']),
                ('Which Ice Raises Sea Level',
                 'Floating sea ice already displaces its own weight so melting it leaves sea '
                 'level unchanged, whereas loss from a land-based ice sheet adds new water to the '
                 'ocean, so Greenland and Antarctica set the rate of sea-level rise.',
                 ['sea ice', 'ice sheet', 'sea level']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 8
    {
        'unit': 'Atmosphere, Weather, and Climate',
        'about': ('The envelope of air: how it is layered and heated, the variables and '
                  'instruments of a weather map, the systems that produce fronts and severe '
                  'storms, and the difference between a weather event and a climate.'),
        'sections': [],
        'topics': [
            ('Atmospheric Structure and Energy', [
                ('Layers and the Temperature Profile',
                 'Temperature falls with height through the troposphere because that layer is '
                 'heated from below, and rises through the stratosphere because ozone absorbs '
                 'ultraviolet light, and that inversion traps weather in the lower layer.',
                 ['troposphere', 'stratosphere', 'ozone']),
                ('Latitudinal Energy Imbalance',
                 'The tropics absorb more solar energy than they emit while the poles emit more '
                 'than they absorb, and winds and currents carry the surplus poleward, so the '
                 'imbalance rather than the global average drives circulation.',
                 ['insolation', 'energy imbalance', 'albedo']),
                ('The Greenhouse Effect',
                 'Greenhouse gases absorb outgoing infrared radiation and re-emit part of it '
                 'downward, so without them the surface would average about 18 degrees below '
                 'zero Celsius instead of its present value.',
                 ['greenhouse effect', 'infrared', 'radiative balance']),
            ]),
            ('Weather Variables, Instruments, and Maps', [
                ('Measuring Temperature, Pressure, and Humidity',
                 'A barometer measures pressure, a psychrometer compares wet and dry bulb '
                 'readings to give relative humidity and dew point, and an anemometer measures '
                 'wind speed, and a station model packs all of them into one symbol.',
                 ['barometer', 'psychrometer', 'station model']),
                ('Dew Point, Humidity, and Cloud Formation',
                 'Relative humidity compares the vapour present with the maximum the air can '
                 'hold at that temperature, so rising air cools to its dew point and condenses '
                 'cloud at the lifting condensation level.',
                 ['dew point', 'relative humidity', 'condensation']),
                ('Pressure Gradients and Wind',
                 'Air accelerates from high toward low pressure, is deflected to the right in '
                 'the Northern Hemisphere by the Coriolis effect, and crosses isobars at an '
                 'angle near the surface because friction slows it.',
                 ['pressure gradient', 'coriolis effect', 'isobar']),
            ]),
            ('Air Masses, Fronts, and Forecasting', [
                ('Air Masses and Their Source Regions',
                 'An air mass takes the temperature and moisture of the surface it forms over, '
                 'so a continental polar mass brings cold dry air and a maritime tropical mass '
                 'brings warm humid air, and its two-letter name records both qualities.',
                 ['air mass', 'source region', 'maritime tropical']),
                ('Fronts, Cyclones, and Forecast Confidence',
                 'A cold front advances steeply and produces a short band of heavy rain followed '
                 'by clearing, a warm front slopes gently and produces long light precipitation, '
                 'and forecast confidence falls with lead time as model solutions diverge.',
                 ['cold front', 'warm front', 'forecast']),
            ]),
            ('Severe Weather', [
                ('Thunderstorms and Tornadoes',
                 'A thunderstorm needs moisture, instability and lift, and when wind shear tilts '
                 'the updraft it begins to rotate as a mesocyclone from which a tornado can '
                 'descend.',
                 ['thunderstorm', 'wind shear', 'mesocyclone']),
                ('Tropical Cyclones: Requirements and Hazards',
                 'A tropical cyclone needs ocean water warmer than about 26 degrees Celsius, low '
                 'wind shear and enough Coriolis effect to organise, which is why none forms at '
                 'the equator, and it weakens once it moves over land.',
                 ['tropical cyclone', 'storm surge', 'coriolis']),
            ]),
            ('Climate Systems and Change', [
                ('Climate Controls and Regional Differences',
                 'Climate is the long-term statistics of weather and its controls are latitude, '
                 'altitude, distance from water, ocean currents, prevailing wind and topography, '
                 'so two places at the same latitude can have different climates.',
                 ['climate', 'climate controls', 'continentality']),
                ('Natural and Human Forcing',
                 'Solar variation, volcanic aerosols and orbital cycles are natural forcings '
                 'while greenhouse gases, aerosols and land use are human ones, and a human cause '
                 'is confirmed when the observed pattern, such as stratospheric cooling with '
                 'surface warming, matches its signature.',
                 ['radiative forcing', 'attribution', 'aerosol']),
                ('Proxies Extend the Climate Record',
                 'Ice cores preserve trapped air and oxygen isotopes, tree rings record growth '
                 'year by year and sediments preserve microfossils, so proxies reach beyond the '
                 'instrumental record although each has its own dating limits.',
                 ['proxy', 'ice core', 'paleoclimate']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 9
    {
        'unit': 'Resources, Hazards, and Human Sustainability',
        'about': ('Earth science applied: where resources come from, how human activity '
                  'changes the systems already described, how hazard and risk differ, what an '
                  'engineering fix trades away, and what sustainability would require.'),
        'sections': [],
        'topics': [
            ('Natural Resources and Energy', [
                ('Renewable, Nonrenewable, and Reserves',
                 'A renewable resource regenerates within a human lifetime and a nonrenewable '
                 'one does not, while a reserve is the part of a resource that is known and '
                 'economically recoverable, so a reserve can grow with price or technology and '
                 'no new discovery.',
                 ['renewable resource', 'reserve', 'resource']),
                ('Fossil Fuel Formation and Trapping',
                 'Coal forms from compressed swamp vegetation while oil and gas form from marine '
                 'organic matter buried in a source rock, then migrate into a porous reservoir '
                 'sealed by a trap, so a field needs all three elements present.',
                 ['fossil fuel', 'source rock', 'petroleum trap']),
                ('Energy Density, Capacity Factor, and the Grid',
                 'A fuel stores far more energy per kilogram than a battery and a wind or solar '
                 'plant produces at a low capacity factor, so replacing firm generation needs '
                 'storage or backup rather than nameplate capacity alone.',
                 ['energy density', 'capacity factor', 'grid']),
            ]),
            ('Human Impacts on Earth Systems', [
                ('Impervious Surfaces and the Urban Water Cycle',
                 'Paving and compaction replace infiltration with runoff, so a city sends a '
                 'larger and faster flood peak into its streams, recharges less groundwater and '
                 'runs warmer than the surrounding countryside.',
                 ['urbanization', 'impervious surface', 'urban heat island']),
                ('Air and Water Pollution Chemistry',
                 'Ground-level ozone forms when sunlight acts on nitrogen oxides and '
                 'hydrocarbons, acid deposition forms when sulphur dioxide and nitrogen oxides '
                 'dissolve in precipitation, and nutrient runoff fuels blooms that consume '
                 'oxygen, so each problem has its own chemistry and its own remedy.',
                 ['ozone', 'acid deposition', 'eutrophication']),
            ]),
            ('Natural Hazards and Risk', [
                ('Risk Is Not the Same as Hazard',
                 'Risk combines the probability of a hazard with the exposure and vulnerability '
                 'of what lies in its path, so an earthquake of one magnitude carries far greater '
                 'risk where buildings are unreinforced.',
                 ['hazard', 'exposure', 'vulnerability']),
                ('Structural and Nonstructural Mitigation',
                 'A levee, retaining wall or seismic brace reduces damage directly while zoning, '
                 'insurance and evacuation reduce exposure, and a levee can raise risk when it '
                 'encourages building behind it and then fails.',
                 ['mitigation', 'zoning', 'levee']),
                ('Recurrence Intervals and Probability',
                 'A recurrence interval is the average interval between events of a given size, '
                 'so a 50-year flood has a two percent chance in any year and two of them can '
                 'still occur in consecutive years.',
                 ['recurrence interval', 'probability', 'return period']),
            ]),
            ('Engineering Solutions and Tradeoffs', [
                ('Criteria and Constraints in Earth Engineering',
                 'A design is judged against criteria such as safety and cost while constrained '
                 'by budget, materials, regulation and site conditions, so a solution is optimal '
                 'only for the constraints it was designed under.',
                 ['design criteria', 'constraint', 'tradeoff']),
                ('Unintended Consequences and Adaptive Management',
                 'A dam that traps sediment starves the delta downstream and accelerates coastal '
                 'retreat, so a large Earth work needs monitoring and adjustment rather than a '
                 'one-time approval.',
                 ['dam', 'sediment starvation', 'monitoring']),
            ]),
            ('Sustainability and Global Change Synthesis', [
                ('Sustainability as Living Within Regeneration Rates',
                 'A use is sustainable only if renewable resources are consumed no faster than '
                 'they regenerate and wastes are released no faster than they are absorbed, so a '
                 'fishery can last only up to its maximum sustainable yield.',
                 ['sustainability', 'regeneration', 'maximum sustainable yield']),
                ('Earth System Feedbacks Amplify or Damp Change',
                 'Melting ice lowering albedo, thawing permafrost releasing carbon and warmer air '
                 'holding more water vapour are positive feedbacks, while increased weathering '
                 'and ocean uptake are negative ones, so the net response depends on which '
                 'balance wins and over what timescale.',
                 ['feedback', 'permafrost', 'carbon cycle']),
                ('Mitigation, Adaptation, and Decisions under Uncertainty',
                 'Mitigation reduces the forcing while adaptation reduces vulnerability to the '
                 'change already committed, and because projections are scenarios rather than '
                 'forecasts, planning weighs outcomes across a range of them.',
                 ['mitigation', 'adaptation', 'scenario']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 10
    {
        'unit': 'Space Systems and Planet Earth',
        'about': ('Where Earth sits: the evidence for an expanding universe, how stars make '
                  "and disperse the elements Earth is built from, the solar system's origin, "
                  'and the Earth-Sun-Moon geometry behind seasons, eclipses and tides.'),
        'sections': [],
        'topics': [
            ('Universe Evidence', [
                ('Evidence for an Expanding Universe',
                 'Distant galaxies show redshifts proportional to their distance, the cosmic '
                 'microwave background is a relic of a hot dense early state and the measured '
                 'hydrogen and helium abundances match prediction, so the three together support '
                 'a hot Big Bang.',
                 ['big bang', 'redshift', 'cosmic microwave background']),
                ('Redshift Is Expansion, Not Motion',
                 'Cosmological redshift grows with distance because space stretches the '
                 'wavelength in transit, so a distant galaxy is not travelling through space at '
                 'the speed its redshift implies but is carried by the expansion between it and '
                 'us.',
                 ['hubble law', 'expansion', 'wavelength']),
                ('Galaxies and the Scale of the Universe',
                 'A galaxy is a gravitationally bound system of stars, gas and dark matter, and '
                 'because the Milky Way is about 100,000 light years across while Andromeda lies '
                 '2.5 million light years away, the spacing between galaxies far exceeds their '
                 'size.',
                 ['galaxy', 'light year', 'milky way']),
            ]),
            ('Stars', [
                ('Star Formation and the Main Sequence',
                 'A collapsing cloud of gas and dust heats until hydrogen fusion begins and '
                 'outward pressure balances gravity, and because a more massive star fuses far '
                 'faster it is brighter but lives a shorter life.',
                 ['star formation', 'main sequence', 'hydrostatic equilibrium']),
                ('Stellar Evolution and Element Synthesis',
                 'A low-mass star ends as a white dwarf after shedding a planetary nebula while a '
                 'high-mass star ends in a supernova that leaves a neutron star or black hole, '
                 'and the heavy elements of Earth were forged in such stars and dispersed by '
                 'supernovae.',
                 ['stellar evolution', 'supernova', 'nucleosynthesis']),
                ('The Hertzsprung-Russell Diagram',
                 'The H-R diagram plots luminosity against surface temperature, and its main '
                 'sequence, giants and white dwarfs occupy separate regions, so a star\'s '
                 'position identifies its stage and relative size.',
                 ['hr diagram', 'luminosity', 'stellar classification']),
            ]),
            ('Solar System Motions and Objects', [
                ('Formation and Differentiation of the Solar System',
                 'The solar nebula flattened into a disk in which dust accreted into '
                 'planetesimals that separated by density, so rocky planets formed where the '
                 'disk was hot and ice-rich giant planets formed beyond the frost line.',
                 ['solar nebula', 'accretion', 'frost line']),
                ("Kepler's Laws and Orbital Speed",
                 'Each planet follows an ellipse with the Sun at one focus and sweeps equal '
                 'areas in equal times, so it moves fastest at perihelion, and the square of its '
                 'orbital period is proportional to the cube of its semi-major axis.',
                 ['kepler law', 'ellipse', 'orbital period']),
            ]),
            ('Earth-Sun Cycles', [
                ('Tilt, Not Distance, Causes the Seasons',
                 'Earth\'s axis is tilted about 23.5 degrees, so each hemisphere receives more '
                 'direct sunlight over longer days for half the year, which is why the two '
                 'hemispheres have opposite seasons even though Earth is nearest the Sun in '
                 'January.',
                 ['axial tilt', 'season', 'solstice']),
                ('Angle of Insolation and Day Length',
                 'Insolation intensity varies with the sine of the Sun\'s angle above the '
                 'horizon, so a low winter Sun spreads the same energy over a longer path and a '
                 'larger area, and beyond the polar circles the day length reaches 24 hours or '
                 'zero.',
                 ['insolation', 'angle of incidence', 'day length']),
                ('Milankovitch Cycles and Ice Ages',
                 'Variations in orbital eccentricity over about 100,000 years, axial tilt over '
                 '41,000 and precession over 23,000 change how sunlight is distributed by season '
                 'at high northern latitudes, which paces glacial and interglacial cycles.',
                 ['milankovitch', 'eccentricity', 'precession']),
            ]),
            ('Moon, Eclipses, and Tides', [
                ('Phases and Eclipses from Orbital Geometry',
                 'The Moon\'s phase depends on how much of its sunlit half faces Earth over a '
                 'cycle of about 29.5 days, and a solar eclipse occurs only at new moon and a '
                 'lunar eclipse only at full moon when the tilted orbit crosses the ecliptic.',
                 ['moon phase', 'eclipse', 'orbital plane']),
                ('Tides from Differential Gravity',
                 'The Moon pulls hardest on the near side of Earth and least on the far side, '
                 'producing two tidal bulges, and the Sun\'s alignment adds to them at new and '
                 'full moon for spring tides and subtracts at the quarter phases for neap '
                 'tides.',
                 ['tide', 'spring tide', 'neap tide']),
            ]),
        ],
    },
]
