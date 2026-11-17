//
// Created by Víctor Jiménez Rugama on 2/4/22.
//
#include <orbis/libkernel.h>
#include "../../include/utils/threadPool.h"
#include "../../include/base.h"
#include "../../include/utils/logger.h"

bool threadPool::shutdown = true;

pthread_mutex_t threadPool::queueMutex = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t threadPool::queueReady = PTHREAD_COND_INITIALIZER;
std::deque<std::function<void()>> threadPool::jobQueue;
std::vector<pthread_t> threadPool::pool;

pthread_mutex_t threadPool::queueMutexSecondary = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t threadPool::queueReadySecondary = PTHREAD_COND_INITIALIZER;
std::deque<std::function<void()>> threadPool::jobQueueSecondary;
std::vector<pthread_t> threadPool::secondaryPool;

int threadPool::init() {
    pthread_mutex_lock(&queueMutex);
    pthread_mutex_lock(&queueMutexSecondary);
    if (!pool.empty() || !secondaryPool.empty()) {
        pthread_mutex_unlock(&queueMutexSecondary);
        pthread_mutex_unlock(&queueMutex);
        return -1;
    }
    shutdown = false;
    jobQueue.clear();
    jobQueueSecondary.clear();
    pthread_mutex_unlock(&queueMutexSecondary);
    pthread_mutex_unlock(&queueMutex);

    pthread_t thread;
    int ret = 0;
    for (int i = 0; i < THREADPOOL_MAIN_POOL_AMOUNT; ++i) {
        ret = pthread_create(&thread, NULL, &threadPool::waitForTask, NULL);
        if (ret != 0) {
            LOG << "Error creating main worker: " << ret;
            term();
            return -1;
        }
        pool.emplace_back(thread);
    }

    for (int i = 0; i < THREADPOOL_SECONDARY_POOL_AMOUNT; ++i) {
        ret = pthread_create(&thread, NULL, &threadPool::waitForTaskSecondary, NULL);
        if (ret != 0) {
            LOG << "Error creating secondary worker: " << ret;
            term();
            return -1;
        }
        secondaryPool.emplace_back(thread);
    }
    return 0;
}

int threadPool::term() {
    pthread_mutex_lock(&queueMutex);
    pthread_mutex_lock(&queueMutexSecondary);
    shutdown = true;
    pthread_cond_broadcast(&queueReady);
    pthread_cond_broadcast(&queueReadySecondary);
    pthread_mutex_unlock(&queueMutexSecondary);
    pthread_mutex_unlock(&queueMutex);

    for (pthread_t threadID : pool) {
        int ret = pthread_join(threadID, NULL);
        if (ret != 0) LOG << "Error joining main worker: " << ret;
    }
    for (pthread_t threadID : secondaryPool) {
        int ret = pthread_join(threadID, NULL);
        if (ret != 0) LOG << "Error joining secondary worker: " << ret;
    }

    pool.clear();
    secondaryPool.clear();
    pthread_mutex_lock(&queueMutex);
    jobQueue.clear();
    pthread_mutex_unlock(&queueMutex);
    pthread_mutex_lock(&queueMutexSecondary);
    jobQueueSecondary.clear();
    pthread_mutex_unlock(&queueMutexSecondary);
    return 0;
}

void *threadPool::waitForTask(void *) {
    for (;;) {
        std::function<void()> job;
        pthread_mutex_lock(&queueMutex);
        while (jobQueue.empty() && !shutdown) {
            pthread_cond_wait(&queueReady, &queueMutex);
        }
        if (shutdown && jobQueue.empty()) {
            pthread_mutex_unlock(&queueMutex);
            return NULL;
        }
        job = jobQueue.front();
        jobQueue.pop_front();
        pthread_mutex_unlock(&queueMutex);

        try {
            job();
        } catch (const std::exception& e) {
            LOG << "Unhandled exception in main worker: " << e.what();
        } catch (...) {
            LOG << "Unknown exception in main worker";
        }
    }
}

void *threadPool::waitForTaskSecondary(void *) {
    for (;;) {
        std::function<void()> job;
        pthread_mutex_lock(&queueMutexSecondary);
        while (jobQueueSecondary.empty() && !shutdown) {
            pthread_cond_wait(&queueReadySecondary, &queueMutexSecondary);
        }
        if (shutdown && jobQueueSecondary.empty()) {
            pthread_mutex_unlock(&queueMutexSecondary);
            return NULL;
        }
        job = jobQueueSecondary.front();
        jobQueueSecondary.pop_front();
        pthread_mutex_unlock(&queueMutexSecondary);

        try {
            job();
        } catch (const std::exception& e) {
            LOG << "Unhandled exception in secondary worker: " << e.what();
        } catch (...) {
            LOG << "Unknown exception in secondary worker";
        }
    }
}

int threadPool::addJob(const std::function<void()>& newJob, bool front) {
    pthread_mutex_lock(&queueMutex);
    if (shutdown || pool.empty()) {
        pthread_mutex_unlock(&queueMutex);
        return -1;
    }
    if (front) jobQueue.emplace_front(newJob);
    else jobQueue.emplace_back(newJob);
    pthread_cond_signal(&queueReady);
    pthread_mutex_unlock(&queueMutex);
    return 0;
}

int threadPool::addJobSecondary(const std::function<void()>& newJob, bool front) {
    pthread_mutex_lock(&queueMutexSecondary);
    if (shutdown || secondaryPool.empty()) {
        pthread_mutex_unlock(&queueMutexSecondary);
        return -1;
    }
    if (front) jobQueueSecondary.emplace_front(newJob);
    else jobQueueSecondary.emplace_back(newJob);
    pthread_cond_signal(&queueReadySecondary);
    pthread_mutex_unlock(&queueMutexSecondary);
    return 0;
}
