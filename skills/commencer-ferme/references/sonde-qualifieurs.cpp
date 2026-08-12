// Sonde : que diagnostique TON compilateur sur les qualifieurs de niveau 2 ?
//
// Les avertissements par defaut varient selon le compilateur et sa version, donc cette
// question se mesure au lieu de se citer. Compiler AVEC les avertissements au maximum,
// puis SANS, et comparer :
//
//   g++     -std=c++20 -Wall -Wextra -Werror -c sonde-qualifieurs.cpp
//   clang++ -std=c++20 -Wall -Wextra -Werror -c sonde-qualifieurs.cpp
//   cl      /std:c++20 /W4 /WX /c sonde-qualifieurs.cpp
//
//   g++     -std=c++20 -w -c sonde-qualifieurs.cpp     # sans aucun avertissement
//
// Ce qu'on cherche : lesquels des trois cas ci-dessous ARRETENT la compilation, et
// lesquels passent en silence. Le troisieme est celui qui compte.

#include <vector>

// CAS 1 -- [[noreturn]] sur une fonction qui peut revenir.
// Attendu : diagnostique (clang -Winvalid-noreturn actif par defaut ; gcc avertit aussi).
// Decommenter pour mesurer.
// [[noreturn]] int ReturnsAnyway(int value) { return value; }

// CAS 2 -- throw DIRECT dans une fonction noexcept.
// Attendu : diagnostique (gcc -Wterminate, clang -Wexceptions, actifs par defaut).
// Decommenter pour mesurer.
// void ThrowsDirectly() noexcept { throw 42; }

// CAS 3 -- LE CAS QUI COMPTE : throw INDIRECT depuis un appele.
// Attendu : AUCUN diagnostic, meme sous -Wall -Wextra -Werror. push_back peut lever
// std::bad_alloc, donc cette fonction peut appeler std::terminate a l'execution.
// C'est la raison pour laquelle noexcept se DERIVE du corps et ne se pose pas par defaut.
void PublishValue(std::vector<int> &sink, int value) noexcept
{
    sink.push_back(value);
}

// La version derivee : la promesse est CALCULEE, pas affirmee. Elle devient fausse toute
// seule si l'appele cesse d'etre noexcept.
void PublishValueDerived(std::vector<int> &sink, int value) noexcept(noexcept(sink.push_back(value)))
{
    sink.push_back(value);
}

int main() { return 0; }
