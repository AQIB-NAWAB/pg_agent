#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int N;
    assert(cin >> N);
    assert(N >= 1 && N <= 2000);
    for (int i = 0; i < N; i++) {
        int x;
        assert(cin >> x);
        assert(x >= -1000 && x <= 1000);
    }
    string extra;
    assert(!(cin >> extra));
    return 0;
}