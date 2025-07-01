#include <bits/stdc++.h>
using namespace std;
int main(){
    ios::sync_with_stdio(false);
    cin.tie(NULL);

    const int T = 6;
    const int N = 2000;
    mt19937_64 rng(chrono::high_resolution_clock::now().time_since_epoch().count());
    uniform_int_distribution<int> dist_all(-1000, 1000);

    vector<vector<int>> tests;
    // 1. all 1000
    tests.emplace_back(N, 1000);
    // 2. all -1000
    tests.emplace_back(N, -1000);
    // 3. alternating 1000, -1000
    vector<int> alt(N);
    for(int i=0;i<N;i++) alt[i] = (i%2==0 ? 1000 : -1000);
    tests.push_back(alt);
    // 4. random uniform
    vector<int> uni(N);
    for(int i=0;i<N;i++) uni[i] = dist_all(rng);
    tests.push_back(uni);
    // 5. sparse non-zero
    vector<int> sparse(N);
    for(int i=0;i<N;i++){
        if(dist_all(rng) % 10 == 0) sparse[i] = (dist_all(rng) > 0 ? 1000 : -1000);
        else sparse[i] = 0;
    }
    tests.push_back(sparse);
    // 6. balanced random but heavy extremes
    vector<int> heavy(N);
    for(int i=0;i<N;i++){
        int x = dist_all(rng);
        if(abs(x) < 500) heavy[i] = (x > 0 ? 1000 : (x < 0 ? -1000 : 0));
        else heavy[i] = x;
    }
    tests.push_back(heavy);

    for(int t = 0; t < T; t++){
        string fname = "test" + to_string(t+1) + ".in";
        ofstream fout(fname);
        fout << N << "\n";
        for(int i = 0; i < N; i++){
            fout << tests[t][i] << (i+1==N ? "\n" : " ");
        }
        fout.close();
    }
    return 0;
}