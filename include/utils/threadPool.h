//
// Created by Víctor Jiménez Rugama on 2/4/22.
//

#ifndef INC_4PT_THREADPOOL_H
#define INC_4PT_THREADPOOL_H

#include <pthread.h>
#include <deque>
#include <functional>
#include <vector>

class threadPool {
private:
    typedef void * (*THREADFUNCPTR)(void *);
    static bool shutdown;

    static pthread_mutex_t queueMutex;
    static pthread_cond_t queueReady;
    static std::deque<std::function<void()>> jobQueue;
    static std::vector<pthread_t> pool;

    static pthread_mutex_t queueMutexSecondary;
    static pthread_cond_t queueReadySecondary;
    static std::deque<std::function<void()>> jobQueueSecondary;
    static std::vector<pthread_t> secondaryPool;

    static void *waitForTask(void *arg);
    static void *waitForTaskSecondary(void *arg);
public:
    static int init();
    static int term();

    static int addJob(const std::function<void()>& newJob, bool front = false);
    static int addJobSecondary(const std::function<void()>& newJob, bool front = false);
};
#endif //INC_4PT_THREADPOOL_H
