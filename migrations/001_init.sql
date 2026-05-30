-- Миграция: начальная схема БД
-- Создание таблиц, индексов и триггера для сервиса smart-cv-analyzer

-- Включаем расширение для генерации UUID
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Задачи обработки
CREATE TABLE tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name    VARCHAR(255) NOT NULL,
    file_type    VARCHAR(10)  NOT NULL CHECK (file_type IN ('pdf', 'docx', 'odt', 'jpeg', 'jpg', 'png')),
    file_size    INTEGER      NOT NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    error_msg    TEXT,
    page_count   SMALLINT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Основная запись резюме (связана с task)
CREATE TABLE resumes (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id    UUID    NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    raw_json   JSONB   NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Персональные данные
CREATE TABLE personal_data (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id   UUID        NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    last_name   VARCHAR(255),
    first_name  VARCHAR(255),
    middle_name VARCHAR(255),
    email       VARCHAR(255),
    phone       VARCHAR(50),
    city        VARCHAR(255),
    birth_date  DATE
);

-- Образование
CREATE TABLE education (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id   UUID NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    institution TEXT,
    specialty   TEXT,
    level       VARCHAR(100),
    start_year  SMALLINT,
    end_year    SMALLINT
);

-- Опыт работы
CREATE TABLE experience (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id        UUID NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    company          TEXT,
    position         TEXT,
    start_date       DATE,
    end_date         DATE,
    responsibilities TEXT
);

-- Навыки
CREATE TABLE skills (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id    UUID NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    technical    JSONB,
    professional JSONB,
    languages    JSONB,
    soft_skills  JSONB
);

-- Дополнительно (сертификаты, проекты, достижения)
CREATE TABLE additional (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id    UUID NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    certificates JSONB,
    projects     JSONB,
    achievements JSONB
);

-- Индексы
CREATE INDEX idx_tasks_status  ON tasks(status);
CREATE INDEX idx_tasks_created ON tasks(created_at DESC);
CREATE INDEX idx_resumes_task  ON resumes(task_id);
CREATE INDEX idx_pd_resume     ON personal_data(resume_id);
CREATE INDEX idx_pd_email      ON personal_data(email);
CREATE INDEX idx_raw_json      ON resumes USING GIN(raw_json);
CREATE INDEX idx_edu_resume    ON education(resume_id);
CREATE INDEX idx_exp_resume    ON experience(resume_id);
CREATE INDEX idx_skills_resume ON skills(resume_id);
CREATE INDEX idx_addl_resume   ON additional(resume_id);

-- Триггер автообновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tasks_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW EXECUTE FUNCTION update_updated_at();
