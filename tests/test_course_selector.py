from argparse import Namespace

from moodle_scraper.course_selector import CourseSelection, CourseSelector
from moodle_scraper.parser import Course


def make_courses() -> list[Course]:
    return [
        Course(id="1", name="Algebra"),
        Course(id="2", name="Hardware"),
        Course(id="3", name="Álgebra avanzada"),
    ]


def test_selection_from_args_and_select_all():
    selector = CourseSelector("https://example.test/itu/")
    selection = CourseSelection.from_args(Namespace(all=True))

    assert selector.select_explicit(make_courses(), selection) == make_courses()


def test_select_existing_course_by_id():
    selector = CourseSelector("https://example.test/itu/")
    selection = CourseSelection(course_id="2")

    assert selector.select_explicit(make_courses(), selection) == [make_courses()[1]]


def test_select_unknown_course_by_id_creates_ad_hoc_course():
    selector = CourseSelector("https://example.test/itu/")
    selection = CourseSelection(course_id="99")

    selected = selector.select_explicit(make_courses(), selection)

    assert selected == [Course(
        id="99",
        name="Curso_99",
        url="https://example.test/itu/course/view.php?id=99",
    )]


def test_filter_returns_matches_and_none_when_it_should_open_menu():
    selector = CourseSelector("https://example.test/itu/")

    assert selector.select_explicit(
        make_courses(), CourseSelection(name_filter="hardware")
    ) == [make_courses()[1]]
    assert selector.select_explicit(
        make_courses(), CourseSelection(name_filter="physics")
    ) is None


def test_parse_indices_supports_ranges_duplicates_and_invalid_values():
    selector = CourseSelector("https://example.test/itu/")

    assert selector.parse_indices("1, 2-3, 3, 99, nope", 3) == [1, 2, 3]


def test_interactive_choice_resolves_all_quit_and_indexes():
    selector = CourseSelector("https://example.test/itu/")
    courses = make_courses()

    assert selector.select_interactive_choice(courses, "q") == []
    assert selector.select_interactive_choice(courses, "a") == courses
    assert selector.select_interactive_choice(courses, "1,3") == [courses[0], courses[2]]
    assert selector.select_interactive_choice(courses, "invalid") is None
