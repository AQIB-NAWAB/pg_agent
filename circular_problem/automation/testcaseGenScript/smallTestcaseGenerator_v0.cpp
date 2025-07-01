#include <bits/stdc++.h>
using namespace std;
int main(){
    ios::sync_with_stdio(false);
    cin.tie(NULL);

    const int TESTS = 60;
    vector<vector<int>> tests;

    // Single-element cases
    tests.push_back({0});
    tests.push_back({1000});
    tests.push_back({-1000});

    // N=2 cases
    tests.push_back({0,0});
    tests.push_back({1000,1000});
    tests.push_back({-1000,-1000});
    tests.push_back({1000,-1000});
    tests.push_back({-1000,1000});
    tests.push_back({1,-1});
    tests.push_back({-1,1});

    // N=3 cases
    tests.push_back({1,2,3});
    tests.push_back({3,2,1});
    tests.push_back({-1,-2,-3});
    tests.push_back({-3,-2,-1});
    tests.push_back({1,-2,3});
    tests.push_back({-1,2,-3});
    tests.push_back({0,1000,-1000});
    tests.push_back({1000,0,-1000});

    // N=4 cases
    tests.push_back({2,2,2,2});
    tests.push_back({-2,-2,-2,-2});
    tests.push_back({0,0,0,0});
    tests.push_back({1,-1,1,-1});
    tests.push_back({-1,1,-1,1});
    tests.push_back({1,1000,-1000,0});

    // N=5 cases
    tests.push_back({1,2,3,4,5});
    tests.push_back({5,4,3,2,1});
    tests.push_back({-1,-2,-3,-4,-5});
    tests.push_back({1000,-1000,1000,-1000,1000});
    tests.push_back({0,1,0,-1,0});

    // Randomized cases
    mt19937 rng(chrono::steady_clock::now().time_since_epoch().count());
    uniform_int_distribution<int> distN(1,50);
    uniform_int_distribution<int> distA(-1000,1000);
    for(int i = tests.size(); i < TESTS; i++){
        int N = distN(rng);
        vector<int> a(N);
        for(int j = 0; j < N; j++){
            a[j] = distA(rng);
        }
        if(i % 4 == 1){
            sort(a.begin(), a.end());
        } else if(i % 4 == 2){
            sort(a.begin(), a.end(), greater<int>());
        } else if(i % 4 == 3){
            for(int j = 0; j < N; j++){
                a[j] = (j % 2 == 0 ? 1000 : -1000);
            }
        }
        tests.push_back(a);
    }

    for(int i = 0; i < TESTS; i++){
        string filename = to_string(i+1) + ".in";
        ofstream ofs(filename);
        int N = tests[i].size();
        ofs << N << "\n";
        for(int j = 0; j < N; j++){
            ofs << tests[i][j] << (j+1==N ? "" : " ");
        }
        ofs << "\n";
        ofs.close();
    }

    return 0;
}